"""Trailing stop domain logic — pure functions, no I/O."""

from __future__ import annotations

import re

from bot.domain.enums import Side, TrailMode
from bot.domain.numbers import format_price
from bot.domain.exchange_trailing import validate_trailing_for_exchange
from bot.domain.models import ParsedStopLoss, StopLoss, Trade  # noqa: TC001
from bot.domain.numbers import parse_number
from bot.domain.results import Failure, Success, failure, success

# Same flexible separators as TP lines: space, comma, dash, etc.
# \s+(?=[\d$]) — bare space only when activation starts with a digit (not " - 96000").
_TRAIL_ACT_SEP = r"(?:\s*[-—|/,]\s*|\s+(?=[\d$])|@\s*|activate(?:\s+at)?:?\s*)"

_SL_TRAIL_RE = re.compile(
    r"^trail\s+"
    r"(?P<value>[\d.,]+)\s*(?P<unit>%)?"
    rf"(?:{_TRAIL_ACT_SEP}(?P<activation>[\d.,$ ]+))?"
    r"(?:\s+stop\s+(?P<pre_stop>[\d.,]+))?"
    r"\s*$",
    re.IGNORECASE,
)


def parse_sl_line(exchange: str, line: str, side: Side) -> Success[ParsedStopLoss] | Failure:
    """Parse ``SL: ...`` / ``Stop: ...`` into fixed or trailing config."""
    body = line.split(":", 1)[1].strip()
    lower = body.lower()

    if lower.startswith("trail"):
        m = _SL_TRAIL_RE.match(body)
        if not m:
            return failure(
                "Invalid trailing SL. Examples:\n"
                "• SL: trail 3%\n"
                "• SL: trail 500\n"
                "• SL: trail 3% - 96000"
            )
        value = parse_number(m.group("value"))
        if value <= 0:
            return failure("Trailing value must be > 0")
        is_percent = m.group("unit") == "%"
        mode = TrailMode.PERCENT if is_percent else TrailMode.DISTANCE
        activation = (
            parse_number(m.group("activation")) if m.group("activation") else None
        )
        pre_stop = (
            parse_number(m.group("pre_stop")) if m.group("pre_stop") else None
        )
        err = validate_trailing_for_exchange(
            exchange, mode, has_activation=activation is not None,
        )
        if err:
            return failure(err)
        if mode == TrailMode.PERCENT and value > 50:
            return failure("Trailing percent seems too large (max 50%)")
        seed = activation or 0.0
        return success(
            ParsedStopLoss(
                trail_mode=mode,
                price=seed,
                trail_value=value,
                activation_price=activation,
                pre_activation_stop=pre_stop,
            )
        )

    try:
        price = parse_number(body)
    except ValueError:
        return failure(f"Invalid SL: {line}")
    if price <= 0:
        return failure("SL price must be > 0")
    return success(ParsedStopLoss(trail_mode=TrailMode.FIXED, price=price))


def is_trailing(sl: StopLoss | ParsedStopLoss | None) -> bool:
    return sl is not None and sl.trail_mode != TrailMode.FIXED


def sl_is_live(sl: StopLoss | None) -> bool:
    """Trailing SL triggers only after activation; fixed SL is always live."""
    if sl is None:
        return False
    if sl.trail_mode == TrailMode.FIXED:
        return True
    if sl.trail_active:
        return True
    return sl.pre_activation_stop is not None


def effective_sl_price(sl: StopLoss | None) -> float | None:
    """Price level used for SL hit detection."""
    if sl is None:
        return None
    if (
        sl.trail_mode != TrailMode.FIXED
        and not sl.trail_active
        and sl.pre_activation_stop is not None
    ):
        return sl.pre_activation_stop
    return sl.price


def compute_sl_from_extreme(
    side: Side,
    extreme: float,
    mode: TrailMode,
    trail_value: float,
) -> float:
    if mode == TrailMode.PERCENT:
        if side == Side.LONG:
            return extreme * (1 - trail_value / 100)
        return extreme * (1 + trail_value / 100)
    if side == Side.LONG:
        return extreme - trail_value
    return extreme + trail_value


def activation_reached(side: Side, activation: float, *, high: float, low: float) -> bool:
    if side == Side.LONG:
        return high >= activation
    return low <= activation


def _ratchet_sl(side: Side, current: float, candidate: float) -> float:
    if side == Side.LONG:
        return max(current, candidate)
    return min(current, candidate)


def initial_trailing_state(
    config: ParsedStopLoss,
    side: Side,
    reference_price: float,
) -> StopLoss:
    """Build StopLoss row when trade opens or trailing config is first applied."""
    if config.trail_mode == TrailMode.FIXED:
        return StopLoss(
            id=None,
            trade_id=None,
            price=config.price,
            trail_mode=TrailMode.FIXED,
        )

    value = config.trail_value or 0
    activation = config.activation_price

    if activation is None:
        extreme = reference_price
        price = compute_sl_from_extreme(side, extreme, config.trail_mode, value)
        return StopLoss(
            id=None,
            trade_id=None,
            price=price,
            trail_mode=config.trail_mode,
            trail_value=config.trail_value,
            activation_price=None,
            extreme_price=extreme,
            trail_active=True,
        )

    if activation_reached(side, activation, high=reference_price, low=reference_price):
        extreme = (
            max(reference_price, activation)
            if side == Side.LONG
            else min(reference_price, activation)
        )
        price = compute_sl_from_extreme(side, extreme, config.trail_mode, value)
        return StopLoss(
            id=None,
            trade_id=None,
            price=price,
            trail_mode=config.trail_mode,
            trail_value=config.trail_value,
            activation_price=activation,
            extreme_price=extreme,
            trail_active=True,
        )

    price = compute_sl_from_extreme(side, activation, config.trail_mode, value)
    return StopLoss(
        id=None,
        trade_id=None,
        price=price,
        trail_mode=config.trail_mode,
        trail_value=config.trail_value,
        activation_price=activation,
        pre_activation_stop=config.pre_activation_stop,
        extreme_price=None,
        trail_active=False,
    )


def apply_trailing_to_candle(trade: Trade, *, high: float, low: float) -> tuple[StopLoss | None, bool]:
    """Update trailing watermark + SL from candle extremes. Returns (sl, changed)."""
    sl = trade.stop_loss
    if sl is None or sl.trail_mode == TrailMode.FIXED:
        return sl, False

    changed = False
    value = sl.trail_value or 0

    if not sl.trail_active:
        if sl.activation_price is None:
            sl.trail_active = True
            sl.extreme_price = high if trade.side == Side.LONG else low
            changed = True
        elif activation_reached(trade.side, sl.activation_price, high=high, low=low):
            sl.trail_active = True
            sl.extreme_price = (
                max(sl.activation_price, high)
                if trade.side == Side.LONG
                else min(sl.activation_price, low)
            )
            changed = True
        else:
            return sl, False

    if trade.side == Side.LONG:
        new_extreme = max(sl.extreme_price or high, high)
    else:
        new_extreme = min(sl.extreme_price or low, low)

    if sl.extreme_price != new_extreme:
        sl.extreme_price = new_extreme
        changed = True

    candidate = compute_sl_from_extreme(trade.side, new_extreme, sl.trail_mode, value)
    new_price = _ratchet_sl(trade.side, sl.price, candidate)
    if new_price != sl.price:
        sl.price = new_price
        changed = True

    return sl, changed


def apply_trailing_to_spot(trade: Trade, price: float) -> tuple[StopLoss | None, bool]:
    return apply_trailing_to_candle(trade, high=price, low=price)


def parsed_sl_effective_price(
    config: ParsedStopLoss,
    side: Side,
    reference_price: float,
) -> float:
    if config.trail_mode == TrailMode.FIXED:
        return config.price
    sl = initial_trailing_state(config, side, reference_price)
    return effective_sl_price(sl) or sl.price


def format_sl_line(sl: StopLoss | ParsedStopLoss) -> str:
    if sl.trail_mode == TrailMode.FIXED:
        price = sl.price
        return f"SL: {format_price(price)}"
    unit = "%" if sl.trail_mode == TrailMode.PERCENT else ""

    trail_active = getattr(sl, "trail_active", False)
    if sl.pre_activation_stop is not None and not trail_active:
        line = f"SL: {format_price(sl.pre_activation_stop)}"
        line += f"\nSL: trail {sl.trail_value:g}{unit}"
    else:
        line = f"SL: trail {sl.trail_value:g}{unit}"
    if sl.activation_price is not None:
        line += f" - {format_price(sl.activation_price)}"
    return line

