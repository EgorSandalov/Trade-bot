from datetime import datetime, timezone

from bot.domain.candles import Candle, TriggerKind, next_trigger_in_candle, spot_trigger
from bot.domain.enums import EntryType, Side, TradeStatus
from bot.domain.models import StopLoss, Trade

_TS = datetime(2026, 9, 18, 12, 0, tzinfo=timezone.utc)


def _pending_limit(
    side: Side,
    entry: float,
    *,
    reference: float | None,
) -> Trade:
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
        limit_reference_price=reference,
        stop_loss=StopLoss(id=1, trade_id=1, price=entry * 1.01),
    )


class TestLimitSpotTrigger:
    def test_long_breakout_waits_for_rise(self):
        trade = _pending_limit(Side.LONG, 85.0, reference=80.0)
        assert spot_trigger(trade, 82.0) is None
        trigger = spot_trigger(trade, 85.0)
        assert trigger is not None
        assert trigger.price == 85.0

    def test_long_pullback_waits_for_fall(self):
        trade = _pending_limit(Side.LONG, 80.0, reference=85.0)
        assert spot_trigger(trade, 82.0) is None
        trigger = spot_trigger(trade, 80.0)
        assert trigger is not None
        assert trigger.price == 80.0

    def test_short_breakout_waits_for_rise(self):
        trade = _pending_limit(Side.SHORT, 81000.0, reference=80904.0)
        assert spot_trigger(trade, 80904.0) is None
        trigger = spot_trigger(trade, 81000.0)
        assert trigger is not None
        assert trigger.price == 81000.0

    def test_short_pullback_waits_for_fall(self):
        trade = _pending_limit(Side.SHORT, 6.18, reference=6.25)
        assert spot_trigger(trade, 6.22) is None
        trigger = spot_trigger(trade, 6.18)
        assert trigger is not None
        assert trigger.price == 6.18

    def test_fill_uses_limit_price_not_spot(self):
        trade = _pending_limit(Side.LONG, 85.0, reference=80.0)
        trigger = spot_trigger(trade, 86.0)
        assert trigger is not None
        assert trigger.price == 85.0

    def test_no_reference_never_fills(self):
        trade = _pending_limit(Side.LONG, 85.0, reference=None)
        assert spot_trigger(trade, 86.0) is None


class TestLimitCandleTrigger:
    def test_long_breakout_fills_when_high_reaches_entry(self):
        trade = _pending_limit(Side.LONG, 85.0, reference=80.0)
        candle = Candle(_TS, open=82.0, high=85.5, low=81.0, close=85.0)
        trigger = next_trigger_in_candle(trade, candle)
        assert trigger is not None
        assert trigger.kind == TriggerKind.FILL_ENTRY
        assert trigger.price == 85.0

    def test_long_pullback_fills_when_low_reaches_entry(self):
        trade = _pending_limit(Side.LONG, 80.0, reference=85.0)
        candle = Candle(_TS, open=82.0, high=83.0, low=79.5, close=80.0)
        trigger = next_trigger_in_candle(trade, candle)
        assert trigger is not None
        assert trigger.price == 80.0

    def test_short_breakout_no_fill_when_high_below_entry(self):
        trade = _pending_limit(Side.SHORT, 81000.0, reference=80904.0)
        candle = Candle(_TS, open=80800.0, high=80900.0, low=80700.0, close=80850.0)
        assert next_trigger_in_candle(trade, candle) is None

    def test_short_breakout_fills_when_high_reaches_entry(self):
        trade = _pending_limit(Side.SHORT, 81000.0, reference=80904.0)
        candle = Candle(_TS, open=80800.0, high=81050.0, low=80700.0, close=81000.0)
        trigger = next_trigger_in_candle(trade, candle)
        assert trigger is not None
        assert trigger.price == 81000.0
