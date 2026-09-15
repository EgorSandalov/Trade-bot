from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.domain.candles import Candle
from bot.domain.enums import EntryType, LevelStatus, Side, TradeStatus, TrailMode
from bot.domain.models import StopLoss, TakeProfitLevel, Trade
from bot.services.trade_service import TradeService


def _trade(**kwargs) -> Trade:
    created = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    defaults = dict(
        id=10,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.LIMIT,
        status=TradeStatus.PENDING,
        entry_price=95000.0,
        executed_entry_price=None,
        remaining_percent=100.0,
        stop_loss=StopLoss(None, 10, 93000.0, trail_mode=TrailMode.FIXED),
        take_profits=[
            TakeProfitLevel(None, 10, 1, 96000.0, 100.0),
        ],
        created_at=created,
        opened_at=None,
    )
    defaults.update(kwargs)
    return Trade(**defaults)


@pytest.mark.asyncio
async def test_limit_replay_fills_at_candle_time_then_checks_tp(monkeypatch):
    repo = MagicMock()
    stored = _trade()

    async def _save(trade: Trade) -> Trade:
        nonlocal stored
        stored = trade
        return trade

    repo.get_by_id = AsyncMock(side_effect=lambda _id: stored)
    repo.get_events = AsyncMock(return_value=[])
    repo.update = AsyncMock()
    repo.replace_sl = AsyncMock()
    repo.replace_tps = AsyncMock()
    repo.add_event = AsyncMock()
    repo.get_partial_exits = AsyncMock(return_value=[])
    svc = TradeService(repo)

    fill_at = datetime(2026, 9, 9, 12, 5, tzinfo=timezone.utc)
    tp_at = datetime(2026, 9, 9, 12, 10, tzinfo=timezone.utc)
    candles = [
        Candle(ts=fill_at, open=94900.0, high=95100.0, low=94800.0, close=95050.0),
        Candle(ts=tp_at, open=95500.0, high=96100.0, low=95400.0, close=96000.0),
    ]

    monkeypatch.setattr(
        "bot.services.trade_service.fetch_candles",
        AsyncMock(return_value=candles),
    )
    monkeypatch.setattr(
        "bot.services.trade_service.fetch_price",
        AsyncMock(return_value=95800.0),
    )

    result = await svc.check_price_triggers(stored, full_replay=True)

    assert result.status == TradeStatus.CLOSED
    assert result.opened_at == fill_at
    assert result.take_profits[0].executed_at == tp_at
    fill_call = repo.add_event.call_args_list[0]
    assert fill_call.kwargs["at"] == fill_at


@pytest.mark.asyncio
async def test_limit_fill_entry_sets_opened_at_from_candle():
    repo = MagicMock()
    trade = _trade()
    filled = datetime(2026, 9, 9, 12, 7, tzinfo=timezone.utc)
    repo.update = AsyncMock()
    repo.add_event = AsyncMock()
    repo.get_by_id = AsyncMock(return_value=trade)
    svc = TradeService(repo)

    await svc.fill_entry(trade, 95000.0, filled_at=filled)

    assert trade.opened_at == filled
    assert trade.status == TradeStatus.OPEN
    repo.add_event.assert_called_once()
    assert repo.add_event.call_args.kwargs["at"] == filled


@pytest.mark.asyncio
async def test_replay_since_for_pending_starts_at_message_time():
    svc = TradeService(MagicMock())
    created = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    trade = _trade(created_at=created)
    now = datetime(2026, 9, 9, 16, 0, tzinfo=timezone.utc)
    since = svc._replay_since(trade, now, full_replay=True, events=[])
    assert since == created
