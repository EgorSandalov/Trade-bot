"""Validate trade parameter edits against current state."""

from __future__ import annotations

from bot.domain.enums import EntryType, LevelStatus, Side, TradeStatus
from bot.domain.models import ParsedTrade, Trade
from bot.domain.parser import parse_trade_message, validate_price_levels
from bot.domain.results import Failure
from bot.domain.trailing import (
    initial_trailing_state,
    is_trailing,
    parsed_sl_effective_price,
    sl_is_live,
)
from bot.domain.numbers import format_price
from bot.utils.trade_setup import parse_indexed_take_profits, split_edit_message


def _price_label(v: float) -> str:
    return format_price(v)


def _entry_for_validation(trade: Trade, parsed: ParsedTrade) -> float:
    if parsed.entry_type == EntryType.MARKET:
        return trade.effective_entry
    if parsed.entry_price is None:
        return trade.effective_entry
    return parsed.entry_price


def _levels_reference(
    trade: Trade,
    parsed: ParsedTrade,
    current_price: float | None,
) -> tuple[float, str]:
    """Open trades: validate SL/TP vs market; pending/new edits use Entry."""
    if (
        current_price is not None
        and trade.status in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED)
    ):
        return current_price, "market"
    return _entry_for_validation(trade, parsed), "Entry"


def _would_trigger_sl(side: Side, market: float, sl: float) -> bool:
    return (side == Side.LONG and market <= sl) or (side == Side.SHORT and market >= sl)


def _would_trigger_tp(side: Side, market: float, tp: float) -> bool:
    return (side == Side.LONG and market >= tp) or (side == Side.SHORT and market <= tp)


def validate_trade_edit(
    trade: Trade,
    raw_text: str,
    current_price: float | None,
) -> tuple[ParsedTrade | None, str | None, list[str]]:
    """
    Parse and validate an edit submission.
    Returns (parsed, reason, errors). On success errors is empty.
    """
    setup_text, reason = split_edit_message(raw_text)
    allow_missing_entry = trade.status in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED)
    parsed_or_err = parse_trade_message(setup_text, allow_missing_entry=allow_missing_entry)
    if isinstance(parsed_or_err, Failure):
        return None, reason, [parsed_or_err.error]

    parsed = parsed_or_err.value
    errors: list[str] = []
    indexed_tps = parse_indexed_take_profits(setup_text)

    if parsed.exchange.lower() != trade.exchange.lower():
        errors.append("Cannot change exchange.")
    if parsed.symbol.upper() != trade.symbol.upper():
        errors.append("Cannot change pair/ticker.")
    if parsed.side != trade.side:
        errors.append("Cannot change direction (LONG/SHORT).")
    if parsed.entry_type != trade.entry_type:
        errors.append("Cannot change Type (market/limit/open).")

    if trade.entry_type == EntryType.MARKET and parsed.entry_price is not None:
        errors.append("Remove Entry line — market type uses live price at open.")

    if trade.status in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED):
        if parsed.entry_price is not None:
            errors.append("Remove Entry line — entry is locked after the trade is open.")

    triggered = [tp for tp in trade.take_profits if tp.status == LevelStatus.TRIGGERED]
    triggered_indices = {tp.order_index for tp in triggered}
    for idx, _, _ in indexed_tps:
        if idx in triggered_indices:
            errors.append(
                f"TP{idx} already hit — remove it from your edit. "
                f"Only set TPs for the remaining {trade.remaining_percent:.0f}%."
            )

    new_tp_sum = sum(pct for _, _, pct in indexed_tps)
    remaining = trade.remaining_percent
    if new_tp_sum > remaining + 0.01:
        closed = 100.0 - remaining
        errors.append(
            f"TP close % sum is {new_tp_sum:.0f}%, but only {remaining:.0f}% remains "
            f"({closed:.0f}% already closed)."
        )

    if any(pct <= 0 for _, _, pct in indexed_tps):
        errors.append("Each TP close % must be > 0.")

    ref_price, ref_label = _levels_reference(trade, parsed, current_price)
    sl_preview = initial_trailing_state(parsed.stop_loss, trade.side, ref_price)
    # Trailing: use pre-activation stop before activation, live trailing SL after activation.
    sl_eff = parsed_sl_effective_price(parsed.stop_loss, trade.side, ref_price)
    all_level_errors = validate_price_levels(
        ref_price,
        trade.side,
        sl_eff,
        parsed.take_profits,
        reference_label=ref_label,
    )
    if trade.status in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED):
        # Open/partial: SL may be above Entry (breakeven); checked vs market below.
        level_errors = [e for e in all_level_errors if e.startswith("TP")]
    elif is_trailing(parsed.stop_loss) and not sl_preview.trail_active:
        level_errors = [e for e in all_level_errors if e.startswith("TP")]
    else:
        level_errors = all_level_errors
    errors.extend(level_errors)

    if current_price is not None and trade.status in (
        TradeStatus.OPEN,
        TradeStatus.PARTIALLY_CLOSED,
    ):
        check_sl = sl_preview if is_trailing(parsed.stop_loss) else None
        sl_live = sl_is_live(check_sl) if check_sl else True
        if sl_live and _would_trigger_sl(trade.side, current_price, sl_eff):
            errors.append(
                f"New SL ({_price_label(sl_eff)}) would trigger immediately "
                f"at market {_price_label(current_price)}. "
                "Adjust SL or close the remaining size manually."
            )
        for _, tp_price, tp_pct in indexed_tps:
            if _would_trigger_tp(trade.side, current_price, tp_price):
                errors.append(
                    f"TP at {_price_label(tp_price)} ({tp_pct:.0f}%) is already reachable "
                    f"at market {_price_label(current_price)} — "
                    f"would close {tp_pct:.0f}% immediately. "
                    "If that is intended, close manually instead of editing TPs."
                )

    if trade.status == TradeStatus.PENDING and current_price is not None:
        if parsed.entry_type == EntryType.LIMIT and parsed.entry_price is not None:
            sl_check = parsed_sl_effective_price(
                parsed.stop_loss, trade.side, parsed.entry_price or trade.effective_entry,
            )
            if _would_trigger_sl(trade.side, current_price, sl_check):
                errors.append(
                    f"New SL ({_price_label(sl_check)}) is on the wrong side of "
                    f"market {_price_label(current_price)} for this {trade.side.value.upper()}."
                )

    if errors:
        return parsed, reason, errors
    return parsed, reason, []
