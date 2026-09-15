from bot.config import BREAKEVEN_THRESHOLD_PCT
from bot.domain.enums import Side

# BE: 0 … +0.2% → −1 pt flat
# Small loss: −1% … 0 → −1 + personal / 20
# Below −1% → full formula: clean + personal / 20


def is_small_loss_zone(clean_move: float) -> bool:
    """Small loss: clean from −1% to 0% (exclusive of 0)."""
    return -1 <= clean_move < 0


def normalize_leverage(leverage: int) -> int:
    return abs(leverage)


def is_breakeven_close(clean_move_pct: float) -> bool:
    """Breakeven label: clean move from 0% to +0.2%."""
    return 0 <= clean_move_pct <= BREAKEVEN_THRESHOLD_PCT


def is_be_for_stats(clean_move: float) -> bool:
    """Exclude from avg win/loss stats (breakeven zone)."""
    return is_breakeven_close(clean_move)


def calc_trade_points(clean_move: float, personal_move: float, force_bu: bool = False) -> float:
    if force_bu or is_breakeven_close(clean_move):
        return -1.0
    if is_small_loss_zone(clean_move):
        return round(-1.0 + personal_move / 20.0, 2)
    return round(clean_move + personal_move / 20.0, 2)


def clean_move_pct(entry: float, exit_price: float, side: Side) -> float:
    if entry <= 0:
        return 0.0
    if side == Side.LONG:
        return (exit_price - entry) / entry * 100
    return (entry - exit_price) / entry * 100


def personal_move_pct(clean_move: float, leverage: int) -> float:
    return clean_move * normalize_leverage(leverage)


def weighted_avg_exit(exits: list[tuple[float, float]]) -> float | None:
    total = sum(f for _, f in exits)
    if total <= 0:
        return None
    return sum(p * f for p, f in exits) / total


def trade_result_clean_move(
    entry: float, side: Side, exits: list[tuple[float, float]]
) -> float:
    total = 0.0
    for price, fraction in exits:
        move = clean_move_pct(entry, price, side)
        total += move * fraction
    return round(total, 2)


def validate_tp_order(side: Side, entry: float, prices: list[float]) -> str | None:
    if side == Side.LONG:
        for i in range(1, len(prices)):
            if prices[i] <= prices[i - 1]:
                return "TP for LONG must be ascending"
    else:
        for i in range(1, len(prices)):
            if prices[i] >= prices[i - 1]:
                return "TP for SHORT must be descending"
    for p in prices:
        if side == Side.LONG and p <= entry:
            return "TP for LONG must be above Entry"
        if side == Side.SHORT and p >= entry:
            return "TP for SHORT must be below Entry"
    return None


def recalc_trade_result(clean_move: float, leverage: int, close_reason) -> tuple[float, float]:
    """Return (personal_move, points) for a closed trade."""
    from bot.domain.enums import CloseReason

    lev = normalize_leverage(leverage)
    personal = personal_move_pct(clean_move, lev)
    force_bu = close_reason == CloseReason.BREAKEVEN or is_breakeven_close(clean_move)
    points = calc_trade_points(clean_move, personal, force_bu=force_bu)
    return personal, points
