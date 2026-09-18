from datetime import datetime, timezone

from bot.domain.candles import Candle, TriggerKind, next_trigger_in_candle, spot_trigger
from bot.domain.enums import EntryType, Side, TradeStatus
from bot.domain.models import StopLoss, Trade

_TS = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _pending_limit(side: Side, entry: float) -> Trade:
    return Trade(
        id=1,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="BYBIT",
        symbol="BTCUSDT",
        side=side,
        leverage=10,
        entry_type=EntryType.LIMIT,
        status=TradeStatus.PENDING,
        entry_price=entry,
        executed_entry_price=None,
        stop_loss=StopLoss(id=1, trade_id=1, price=entry * 1.01),
    )


class TestLimitSpotTrigger:
    def test_short_limit_stays_pending_when_market_below_entry(self):
        trade = _pending_limit(Side.SHORT, 81000.0)
        assert spot_trigger(trade, 80904.0) is None

    def test_short_limit_fills_when_market_reaches_entry(self):
        trade = _pending_limit(Side.SHORT, 81000.0)
        trigger = spot_trigger(trade, 81000.0)
        assert trigger is not None
        assert trigger.kind == TriggerKind.FILL_ENTRY
        assert trigger.price == 81000.0

    def test_short_limit_fills_at_limit_not_spot(self):
        trade = _pending_limit(Side.SHORT, 81000.0)
        trigger = spot_trigger(trade, 81200.0)
        assert trigger is not None
        assert trigger.price == 81000.0

    def test_long_limit_stays_pending_when_market_above_entry(self):
        trade = _pending_limit(Side.LONG, 95000.0)
        assert spot_trigger(trade, 95500.0) is None

    def test_long_limit_fills_when_market_falls_to_entry(self):
        trade = _pending_limit(Side.LONG, 95000.0)
        trigger = spot_trigger(trade, 95000.0)
        assert trigger is not None
        assert trigger.kind == TriggerKind.FILL_ENTRY
        assert trigger.price == 95000.0

    def test_long_limit_fills_at_limit_not_spot(self):
        trade = _pending_limit(Side.LONG, 95000.0)
        trigger = spot_trigger(trade, 94800.0)
        assert trigger is not None
        assert trigger.price == 95000.0


class TestLimitCandleTrigger:
    def test_short_limit_no_fill_when_high_below_entry(self):
        trade = _pending_limit(Side.SHORT, 81000.0)
        candle = Candle(_TS, open=80800.0, high=80900.0, low=80700.0, close=80850.0)
        assert next_trigger_in_candle(trade, candle) is None

    def test_short_limit_fills_when_high_reaches_entry(self):
        trade = _pending_limit(Side.SHORT, 81000.0)
        candle = Candle(_TS, open=80800.0, high=81050.0, low=80700.0, close=81000.0)
        trigger = next_trigger_in_candle(trade, candle)
        assert trigger is not None
        assert trigger.kind == TriggerKind.FILL_ENTRY
        assert trigger.price == 81000.0

    def test_long_limit_no_fill_when_low_above_entry(self):
        trade = _pending_limit(Side.LONG, 95000.0)
        candle = Candle(_TS, open=95200.0, high=95500.0, low=95100.0, close=95300.0)
        assert next_trigger_in_candle(trade, candle) is None

    def test_long_limit_fills_when_low_reaches_entry(self):
        trade = _pending_limit(Side.LONG, 95000.0)
        candle = Candle(_TS, open=95200.0, high=95300.0, low=94900.0, close=95000.0)
        trigger = next_trigger_in_candle(trade, candle)
        assert trigger is not None
        assert trigger.kind == TriggerKind.FILL_ENTRY
        assert trigger.price == 95000.0
