import re

from bot.domain.enums import EntryType, Side
from bot.domain.exchanges import is_supported_exchange, normalize_exchange
from bot.domain.models import ParsedStopLoss, ParsedTrade
from bot.domain.enums import TrailMode
from bot.domain.numbers import parse_number
from bot.domain.trailing import is_trailing, parse_sl_line, parsed_sl_effective_price
from bot.domain.results import Failure, Success, failure, success

ENTRY_TYPE_MAP = {
    "market": EntryType.MARKET,
    "limit": EntryType.LIMIT,
    "open": EntryType.OPEN,
}

TP_PATTERN = re.compile(
    r"^TP\s*(\d+)\s*[:：]\s*([\d.,]+)\s*(?:[-—|/]\s*|\s+|,\s+)([\d.,]+)\s*%?\s*$",
    re.IGNORECASE,
)

ParseResult = Success[ParsedTrade] | Failure

_SETUP_FIELD_PREFIXES = ("type:", "leverage:", "entry:", "comment:", "sl:", "stop:")


def _is_setup_field_line(line: str) -> bool:
    lower = line.lower()
    if lower.startswith(_SETUP_FIELD_PREFIXES):
        return True
    return TP_PATTERN.match(line) is not None


def looks_like_setup(body: str) -> bool:
    """True when a multi-line message resembles a trade setup (for General-topic warnings)."""
    lines = [ln.strip() for ln in body.strip().splitlines() if ln.strip()]
    if len(lines) < 3:
        return False
    if not is_supported_exchange(lines[0]):
        return False
    if lines[2].upper() in ("LONG", "SHORT"):
        return True
    return any(_is_setup_field_line(line) for line in lines[1:])


def _parse_entry_type(line: str) -> EntryType | None:
    key = line.strip().lower()
    if key.startswith("type:"):
        key = key.split(":", 1)[1].strip()
    return ENTRY_TYPE_MAP.get(key)


def validate_price_levels(
    reference_price: float,
    side: Side,
    stop_loss: float,
    take_profits: list[tuple[float, float]],
    *,
    reference_label: str = "Entry",
) -> list[str]:
    """Check SL/TP are on the correct side of ``reference_price`` (Entry or live market)."""
    errors: list[str] = []
    if side == Side.LONG:
        if stop_loss >= reference_price:
            errors.append(f"SL for LONG must be below {reference_label}")
        for price, _ in take_profits:
            if price <= reference_price:
                errors.append(f"TP for LONG must be above {reference_label}")
    else:
        if stop_loss <= reference_price:
            errors.append(f"SL for SHORT must be above {reference_label}")
        for price, _ in take_profits:
            if price >= reference_price:
                errors.append(f"TP for SHORT must be below {reference_label}")
    return errors


def parse_trade_message(text: str) -> ParseResult:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 6:
        return failure(
            "Not enough lines. Minimum: exchange, symbol, side, type, leverage, SL, TP."
        )

    exchange = normalize_exchange(lines[0])
    if not is_supported_exchange(exchange):
        from bot.domain.exchanges import exchanges_list

        return failure(f"Unsupported exchange. Available: {exchanges_list()}")

    symbol = lines[1].upper().replace("USDT", "").replace("/", "")
    if not symbol.endswith("USDT"):
        symbol = symbol + "USDT"

    side_raw = lines[2].upper()
    if side_raw not in ("LONG", "SHORT"):
        return failure(f"Line 3: direction must be LONG or SHORT, got: {lines[2]}")
    side = Side.LONG if side_raw == "LONG" else Side.SHORT

    entry_type = _parse_entry_type(lines[3])
    if not entry_type:
        return failure("Line 4: Type must be market, limit, or open")

    leverage: int | None = None
    entry_price: float | None = None
    stop_loss: ParsedStopLoss | None = None
    pending_fixed_sl: float | None = None
    take_profits: list[tuple[float, float]] = []
    comment: str | None = None

    def _attach_sl(parsed_sl: ParsedStopLoss) -> Failure | None:
        nonlocal stop_loss, pending_fixed_sl
        if parsed_sl.trail_mode == TrailMode.FIXED:
            if (
                stop_loss is not None
                and is_trailing(stop_loss)
                and stop_loss.activation_price is not None
            ):
                if stop_loss.pre_activation_stop is not None:
                    return failure("Only one fixed SL before trailing activation")
                stop_loss.pre_activation_stop = parsed_sl.price
                return None
            if stop_loss is not None or pending_fixed_sl is not None:
                return failure("Conflicting SL lines — use fixed + one trailing, or one SL only")
            pending_fixed_sl = parsed_sl.price
            return None

        if stop_loss is not None:
            return failure("Only one trailing SL allowed")
        if parsed_sl.activation_price is not None:
            if pending_fixed_sl is not None:
                parsed_sl.pre_activation_stop = pending_fixed_sl
                pending_fixed_sl = None
            elif parsed_sl.pre_activation_stop is None:
                return failure(
                    "Trailing with activation needs a fixed SL before activation.\n"
                    "Add SL: 75000, then SL: trail 0,5% - 80000"
                )
        elif pending_fixed_sl is not None:
            return failure("Extra fixed SL — trailing without activation uses one SL line only")
        stop_loss = parsed_sl
        return None

    for line in lines[4:]:
        lower = line.lower()

        if lower.startswith("comment:"):
            comment = line.split(":", 1)[1].strip()
            continue

        if lower.startswith("leverage:"):
            val = line.split(":", 1)[1].strip().lower().replace("x", "")
            try:
                leverage = int(float(val))
            except ValueError:
                return failure(f"Invalid leverage: {line}")
            continue

        if lower.startswith("entry:"):
            try:
                entry_price = parse_number(line.split(":", 1)[1])
            except ValueError:
                return failure(f"Invalid entry: {line}")
            continue

        if lower.startswith("sl:") or lower.startswith("stop:"):
            sl_result = parse_sl_line(exchange, line, side)
            if isinstance(sl_result, Failure):
                return sl_result
            err = _attach_sl(sl_result.value)
            if err:
                return err
            continue

        tp_match = TP_PATTERN.match(line)
        if tp_match:
            price = parse_number(tp_match.group(2))
            pct = parse_number(tp_match.group(3))
            take_profits.append((price, pct))
            continue

        return failure(f"Unknown line: {line}")

    if pending_fixed_sl is not None and stop_loss is None:
        stop_loss = ParsedStopLoss(trail_mode=TrailMode.FIXED, price=pending_fixed_sl)
    elif pending_fixed_sl is not None:
        return failure("Fixed SL must be paired with trailing that has activation")

    errors: list[str] = []
    if leverage is None:
        errors.append("Leverage: 10")
    elif leverage < 1:
        errors.append("Leverage must be >= 1")
    if entry_type != EntryType.MARKET and entry_price is None:
        errors.append("Entry: 95000  (required for limit and open)")
    if entry_type == EntryType.MARKET and entry_price is not None:
        errors.append("Entry: omit for market type (price is fetched automatically)")
    if stop_loss is None:
        errors.append("SL: 93000")
    if not take_profits:
        errors.append("TP1: 96000 - 50%")

    if errors:
        return failure("Missing or invalid fields:\n• " + "\n• ".join(errors))

    if leverage < 1:
        return failure("Leverage must be >= 1 (e.g. Leverage: 10)")

    total_tp = sum(p for _, p in take_profits)
    if total_tp > 100:
        return failure(f"Sum of TP close % = {total_tp:.0f}%, maximum 100%")
    if any(p <= 0 for _, p in take_profits):
        return failure("Each TP close % must be > 0")

    return success(
        ParsedTrade(
            exchange=exchange,
            symbol=symbol,
            side=side,
            leverage=leverage,  # type: ignore[arg-type]
            entry_price=entry_price,
            entry_type=entry_type,
            stop_loss=stop_loss,
            take_profits=take_profits,
            comment=comment,
        )
    )
