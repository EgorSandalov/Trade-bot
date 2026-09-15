from datetime import datetime, timezone

import pytest

from bot.domain.candles import Candle, next_trigger_in_candle, spot_trigger
from bot.domain.enums import EntryType, LevelStatus, Side, TradeStatus
from bot.domain.models import StopLoss, TakeProfitLevel, Trade


def _trade(**kwargs) -> Trade:
    defaults = dict(
        id=1,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="MEXC",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.OPEN,
        entry_price=80000.0,
        executed_entry_price=80000.0,
        stop_loss=StopLoss(None, 1, 79000.0),
        take_profits=[
            TakeProfitLevel(None, 1, 1, 81000.0, 100.0),
        ],
        opened_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return Trade(**defaults)


def test_long_tp_hit_on_candle_high():
    trade = _trade()
    candle = Candle(
        ts=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        open=80500.0,
        high=81200.0,
        low=80400.0,
        close=80600.0,
    )
    trigger = next_trigger_in_candle(trade, candle)
    assert trigger is not None
    assert trigger.tp_index == 1
    assert trigger.price == 81000.0


def test_long_sl_hit_when_price_dropped_during_downtime():
    """Low touched SL but high stayed below TP — SL closes even if price reverted."""
    trade = _trade()
    candle = Candle(
        ts=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        open=80500.0,
        high=80800.0,
        low=78800.0,
        close=80500.0,
    )
    trigger = next_trigger_in_candle(trade, candle)
    assert trigger is not None
    assert trigger.kind.value == "sl"


def test_long_tp_hit_when_high_touched_tp_but_price_reverted():
    """High touched TP while current/close is below TP — still counts after downtime."""
    trade = _trade()
    candle = Candle(
        ts=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        open=80500.0,
        high=81200.0,
        low=80400.0,
        close=80500.0,
    )
    trigger = next_trigger_in_candle(trade, candle)
    assert trigger is not None
    assert trigger.kind.value == "tp"


def test_long_tp_before_sl_when_open_closer_to_tp():
    trade = _trade(
        stop_loss=StopLoss(None, 1, 79000.0),
        take_profits=[TakeProfitLevel(None, 1, 1, 81000.0, 100.0)],
    )
    candle = Candle(
        ts=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        open=80800.0,
        high=81200.0,
        low=78800.0,
        close=80500.0,
    )
    trigger = next_trigger_in_candle(trade, candle)
    assert trigger is not None
    assert trigger.kind.value == "tp"


def test_spot_does_not_see_reverted_tp_if_current_below_tp():
    trade = _trade()
    trigger = spot_trigger(trade, 80500.0)
    assert trigger is None


def test_limit_long_entry_on_candle_high():
    trade = _trade(
        entry_type=EntryType.LIMIT,
        status=TradeStatus.PENDING,
        entry_price=80000.0,
        executed_entry_price=None,
        opened_at=None,
    )
    candle = Candle(
        ts=datetime(2026, 1, 1, 12, 1, tzinfo=timezone.utc),
        open=79800.0,
        high=80100.0,
        low=79700.0,
        close=79900.0,
    )
    trigger = next_trigger_in_candle(trade, candle)
    assert trigger is not None
    assert trigger.kind.value == "fill_entry"


def test_short_sl_on_candle_high():
    trade = _trade(
        side=Side.SHORT,
        entry_price=80000.0,
        executed_entry_price=80000.0,
        stop_loss=StopLoss(None, 1, 81000.0),
        take_profits=[TakeProfitLevel(None, 1, 1, 78000.0, 100.0)],
    )
    candle = Candle(
        ts=datetime(2026, 1, 1, 12, 5, tzinfo=timezone.utc),
        open=80500.0,
        high=81500.0,
        low=79800.0,
        close=80400.0,
    )
    trigger = next_trigger_in_candle(trade, candle)
    assert trigger is not None
    assert trigger.kind.value == "sl"
