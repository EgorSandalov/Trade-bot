from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.domain.candles import Candle
from bot.domain.enums import EntryType, LevelStatus, Side, TradeStatus, TrailMode
from bot.domain.models import StopLoss, Trade
from bot.services.trade_service import TradeService


def _svc(trade: Trade) -> TradeService:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(return_value=trade)
    repo.replace_sl = AsyncMock()
    repo.add_event = AsyncMock()
    return TradeService(repo)


def _trade(**kwargs) -> Trade:
    defaults = dict(
        id=6,
        user_id=1,
        user_name="T",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.OPEN,
        entry_price=79342.0,
        executed_entry_price=79342.0,
        remaining_percent=50.0,
        stop_loss=StopLoss(
            None, 6, 79000.0,
            trail_mode=TrailMode.PERCENT,
            trail_value=3.0,
            extreme_price=81300.0,
            trail_active=True,
        ),
        take_profits=[],
        opened_at=datetime(2026, 9, 9, 12, 29, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return Trade(**defaults)


@pytest.mark.asyncio
async def test_trailing_does_not_false_trigger_sl_after_high_updates_same_candle():
    """High raises trailing SL; low on same bar must not hit the new SL."""
    trade = _trade()
    svc = _svc(trade)
    candle = Candle(
        ts=datetime(2026, 9, 9, 13, 20, tzinfo=timezone.utc),
        open=79800.0,
        high=82000.0,
        low=79300.0,
        close=81000.0,
    )
    result = await svc._apply_candle_history(trade, [candle])
    assert result.status == TradeStatus.OPEN
    assert result.stop_loss is not None
    assert result.stop_loss.status == LevelStatus.PENDING
