from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.domain.enums import EntryType, LevelStatus, Side, TradeStatus
from bot.domain.models import StopLoss, TakeProfitLevel, Trade
from bot.services.trade_service import TradeService


def _trade(**kwargs) -> Trade:
    defaults = dict(
        id=5,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.OPEN,
        entry_price=80000.0,
        executed_entry_price=80000.0,
        remaining_percent=50.0,
        stop_loss=StopLoss(id=1, trade_id=5, price=79000.0),
        take_profits=[
            TakeProfitLevel(
                id=1, trade_id=5, order_index=1, price=79200.0,
                close_percent=50.0, status=LevelStatus.TRIGGERED,
            ),
            TakeProfitLevel(
                id=2, trade_id=5, order_index=2, price=82000.0,
                close_percent=50.0,
            ),
        ],
        opened_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
        last_monitored_at=datetime.now(timezone.utc) - timedelta(minutes=2),
    )
    defaults.update(kwargs)
    return Trade(**defaults)


@pytest.fixture
def trade_service() -> TradeService:
    repo = MagicMock()
    repo.get_by_id = AsyncMock(side_effect=lambda tid: _trade(id=tid))
    repo.get_events = AsyncMock(return_value=[])
    repo.update = AsyncMock()
    return TradeService(repo)


@pytest.mark.asyncio
async def test_check_price_triggers_skipped_when_paused(trade_service: TradeService, monkeypatch):
    trade = _trade()
    trade_service.pause_monitoring(trade.id)

    fetch_candles = AsyncMock()
    fetch_price = AsyncMock(return_value=85000.0)
    monkeypatch.setattr("bot.services.trade_service.fetch_candles", fetch_candles)
    monkeypatch.setattr("bot.services.trade_service.fetch_price", fetch_price)

    result = await trade_service.check_price_triggers(trade)

    fetch_candles.assert_not_called()
    fetch_price.assert_not_called()
    trade_service.repo.update.assert_not_called()
    assert result is trade
    assert result.status == TradeStatus.OPEN


@pytest.mark.asyncio
async def test_check_price_triggers_runs_after_resume(trade_service: TradeService, monkeypatch):
    trade = _trade()
    trade_service.pause_monitoring(trade.id)
    trade_service.resume_monitoring(trade.id)

    fetch_candles = AsyncMock(return_value=[])
    fetch_price = AsyncMock(return_value=81000.0)
    monkeypatch.setattr("bot.services.trade_service.fetch_candles", fetch_candles)
    monkeypatch.setattr("bot.services.trade_service.fetch_price", fetch_price)

    await trade_service.check_price_triggers(trade)

    assert fetch_candles.call_count >= 1
    fetch_price.assert_called_once()
    trade_service.repo.update.assert_called_once()
