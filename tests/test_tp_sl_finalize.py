from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.domain.enums import CloseReason, EntryType, LevelStatus, Side, TradeStatus
from bot.domain.models import StopLoss, TakeProfitLevel, Trade
from bot.services.trade_service import TradeService


def _trade(**kwargs) -> Trade:
    defaults = dict(
        id=1,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.PARTIALLY_CLOSED,
        entry_price=80000.0,
        executed_entry_price=80000.0,
        remaining_percent=50.0,
        stop_loss=StopLoss(id=1, trade_id=1, price=79000.0),
        take_profits=[
            TakeProfitLevel(
                id=1, trade_id=1, order_index=1, price=81000.0,
                close_percent=50.0, status=LevelStatus.TRIGGERED,
                executed_price=81000.0,
            ),
            TakeProfitLevel(
                id=2, trade_id=1, order_index=2, price=82000.0,
                close_percent=50.0,
            ),
        ],
        opened_at=datetime(2026, 1, 1, 12, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return Trade(**defaults)


@pytest.fixture
def trade_service() -> TradeService:
    repo = MagicMock()
    stored = _trade()

    async def get_by_id(_tid: int) -> Trade:
        return stored

    repo.get_by_id = AsyncMock(side_effect=get_by_id)
    repo.update = AsyncMock()
    repo.replace_sl = AsyncMock()
    repo.replace_tps = AsyncMock()
    repo.add_event = AsyncMock()
    repo.get_partial_exits = AsyncMock(return_value=[])
    svc = TradeService(repo)
    svc._stored = stored  # type: ignore[attr-defined]
    return svc


@pytest.mark.asyncio
async def test_trigger_sl_after_tp1_weights_remaining_portion(trade_service: TradeService):
    trade = trade_service._stored  # type: ignore[attr-defined]

    await trade_service.trigger_sl(trade, 79000.0)

    assert trade.status == TradeStatus.CLOSED
    assert trade.close_reason == CloseReason.BREAKEVEN
    assert trade.result_clean_move_pct == pytest.approx(0.0)
    assert trade.avg_exit_price == pytest.approx(80000.0)
