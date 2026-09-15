from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.domain.candles import Candle
from bot.domain.enums import EntryType, Side, TradeStatus, TrailMode
from bot.domain.models import StopLoss, Trade
from bot.services.trade_service import TradeService


@pytest.mark.asyncio
async def test_trailing_sl_event_uses_candle_time_not_processing_time():
    opened = datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc)
    candle_at = datetime(2026, 9, 13, 17, 12, tzinfo=timezone.utc)
    trade = Trade(
        id=8,
        user_id=1,
        user_name="T",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.OPEN,
        entry_price=76870.6,
        executed_entry_price=76870.6,
        remaining_percent=100.0,
        opened_at=opened,
        stop_loss=StopLoss(
            None, 8, 76570.6,
            trail_mode=TrailMode.DISTANCE,
            trail_value=300.0,
            trail_active=True,
            extreme_price=76870.6,
        ),
    )

    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=trade)
    repo.replace_sl = AsyncMock()
    event_calls: list = []

    async def capture_event(trade_id, event_type, description, *, at=None):
        event_calls.append((event_type.value, at))

    repo.add_event = AsyncMock(side_effect=capture_event)

    svc = TradeService(repo)
    candle = Candle(ts=candle_at, open=77350.0, high=77390.0, low=77340.0, close=77380.0)
    await svc._apply_trailing_candle(trade, high=candle.high, low=candle.low, at=candle.ts)

    assert event_calls
    assert event_calls[0][0] == "sl_trailed"
    assert event_calls[0][1] == candle_at
