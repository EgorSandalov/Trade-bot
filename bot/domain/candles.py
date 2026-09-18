"""1m candle replay for SL/TP detection after bot downtime."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from bot.domain.enums import EntryType, LevelStatus, Side, TradeStatus
from bot.domain.models import StopLoss, TakeProfitLevel, Trade
from bot.domain.trailing import effective_sl_price, sl_is_live


@dataclass(frozen=True)
class Candle:
    ts: datetime
    open: float
    high: float
    low: float
    close: float


class TriggerKind(Enum):
    FILL_ENTRY = "fill_entry"
    STOP_LOSS = "sl"
    TAKE_PROFIT = "tp"


@dataclass(frozen=True)
class CandleTrigger:
    kind: TriggerKind
    price: float
    tp_index: int | None = None
    at: datetime | None = None


def next_trigger_in_candle(
    trade: Trade,
    candle: Candle,
    *,
    tp_only: bool = False,
) -> CandleTrigger | None:
    """Next SL/TP/entry trigger inside one candle (chronological heuristic)."""
    if trade.status == TradeStatus.PENDING and trade.entry_type == EntryType.LIMIT:
        entry = trade.entry_price
        hit = (
            (trade.side == Side.LONG and candle.low <= entry)
            or (trade.side == Side.SHORT and candle.high >= entry)
        )
        if hit:
            return CandleTrigger(TriggerKind.FILL_ENTRY, entry, at=candle.ts)
        return None

    if trade.status not in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED):
        return None

    if trade.side == Side.LONG:
        return _next_long_trigger(trade, candle, tp_only=tp_only)
    return _next_short_trigger(trade, candle, tp_only=tp_only)


def _pending_tps(trade: Trade) -> list[TakeProfitLevel]:
    return sorted(
        (tp for tp in trade.take_profits if tp.status == LevelStatus.PENDING),
        key=lambda t: t.order_index,
    )


def _next_long_trigger(
    trade: Trade, candle: Candle, *, tp_only: bool = False,
) -> CandleTrigger | None:
    sl = trade.stop_loss
    sl_level = effective_sl_price(sl)
    sl_hit = (
        not tp_only
        and bool(
            sl
            and sl_level is not None
            and sl.status == LevelStatus.PENDING
            and sl_is_live(sl)
            and candle.low <= sl_level
        )
    )
    hit_tps = [tp for tp in _pending_tps(trade) if candle.high >= tp.price]

    if sl_hit and hit_tps:
        first_tp = hit_tps[0]
        if _long_intrabar_first(candle.open, sl_level, first_tp.price) == "sl":
            return CandleTrigger(TriggerKind.STOP_LOSS, sl_level, at=candle.ts)
        return CandleTrigger(
            TriggerKind.TAKE_PROFIT, first_tp.price, first_tp.order_index, at=candle.ts,
        )

    if sl_hit:
        return CandleTrigger(TriggerKind.STOP_LOSS, sl_level, at=candle.ts)

    if hit_tps:
        tp = hit_tps[0]
        return CandleTrigger(
            TriggerKind.TAKE_PROFIT, tp.price, tp.order_index, at=candle.ts,
        )

    return None


def _next_short_trigger(
    trade: Trade, candle: Candle, *, tp_only: bool = False,
) -> CandleTrigger | None:
    sl = trade.stop_loss
    sl_level = effective_sl_price(sl)
    sl_hit = (
        not tp_only
        and bool(
            sl
            and sl_level is not None
            and sl.status == LevelStatus.PENDING
            and sl_is_live(sl)
            and candle.high >= sl_level
        )
    )
    hit_tps = [tp for tp in _pending_tps(trade) if candle.low <= tp.price]

    if sl_hit and hit_tps:
        first_tp = hit_tps[0]
        if _short_intrabar_first(candle.open, sl_level, first_tp.price) == "sl":
            return CandleTrigger(TriggerKind.STOP_LOSS, sl_level, at=candle.ts)
        return CandleTrigger(
            TriggerKind.TAKE_PROFIT, first_tp.price, first_tp.order_index, at=candle.ts,
        )

    if sl_hit:
        return CandleTrigger(TriggerKind.STOP_LOSS, sl_level, at=candle.ts)

    if hit_tps:
        tp = hit_tps[0]
        return CandleTrigger(
            TriggerKind.TAKE_PROFIT, tp.price, tp.order_index, at=candle.ts,
        )

    return None


def _long_intrabar_first(open_p: float, sl: float, tp: float) -> str:
    if open_p <= sl:
        return "sl"
    if open_p >= tp:
        return "tp"
    if (open_p - sl) <= (tp - open_p):
        return "sl"
    return "tp"


def _short_intrabar_first(open_p: float, sl: float, tp: float) -> str:
    if open_p >= sl:
        return "sl"
    if open_p <= tp:
        return "tp"
    if (sl - open_p) <= (open_p - tp):
        return "sl"
    return "tp"


def spot_trigger(trade: Trade, price: float) -> CandleTrigger | None:
    """Same rules as live tick check (last price)."""
    if trade.status == TradeStatus.PENDING and trade.entry_type == EntryType.LIMIT:
        entry = trade.entry_price
        hit = (
            (trade.side == Side.LONG and price <= entry)
            or (trade.side == Side.SHORT and price >= entry)
        )
        if hit:
            return CandleTrigger(TriggerKind.FILL_ENTRY, entry)
        return None

    if trade.status not in (TradeStatus.OPEN, TradeStatus.PARTIALLY_CLOSED):
        return None

    sl = trade.stop_loss
    sl_level = effective_sl_price(sl)
    if sl and sl.status == LevelStatus.PENDING and sl_is_live(sl) and sl_level is not None:
        hit = (
            (trade.side == Side.LONG and price <= sl_level)
            or (trade.side == Side.SHORT and price >= sl_level)
        )
        if hit:
            return CandleTrigger(TriggerKind.STOP_LOSS, price)

    for tp in _pending_tps(trade):
        hit = (
            (trade.side == Side.LONG and price >= tp.price)
            or (trade.side == Side.SHORT and price <= tp.price)
        )
        if hit:
            return CandleTrigger(TriggerKind.TAKE_PROFIT, price, tp.order_index)

    return None
