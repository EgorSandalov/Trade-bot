from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.domain.enums import EntryType, LevelStatus, Side, TradeStatus
from bot.domain.models import StopLoss, TakeProfitLevel, Trade
from bot.keyboards.menus import neighbor_trade_ids, trade_detail_kb
from bot.domain.enums import Period


def _trade(trade_id: int, num: int) -> Trade:
    opened = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    return Trade(
        id=trade_id,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.LIMIT,
        status=TradeStatus.PARTIALLY_CLOSED,
        entry_price=77000.0,
        executed_entry_price=77000.0,
        remaining_percent=70.0,
        stop_loss=StopLoss(None, trade_id, 76600.0),
        take_profits=[
            TakeProfitLevel(None, trade_id, 1, 77100.0, 10.0, status=LevelStatus.TRIGGERED),
        ],
        opened_at=opened,
        created_at=opened,
        user_trade_number=num,
    )


def test_neighbor_trade_ids_newest_first():
    trades = [_trade(11, 11), _trade(10, 10), _trade(9, 9)]
    prev_id, next_id = neighbor_trade_ids(trades, 10)
    assert prev_id == 9
    assert next_id == 11


def test_trade_detail_kb_includes_nav():
    trades = [_trade(11, 11), _trade(10, 10), _trade(9, 9)]
    kb = trade_detail_kb(10, 42, Period.MONTH, None, trades=trades)
    labels = [btn.text for row in kb.inline_keyboard for btn in row]
    assert "◀ Prev" in labels
    assert "Next ▶" in labels


@pytest.mark.asyncio
async def test_tp_catchup_replays_from_last_tp_when_sl_anchor_is_later(monkeypatch):
    from bot.domain.candles import Candle
    from bot.domain.models import TradeEvent
    from bot.domain.enums import TradeEventType
    from bot.services.trade_service import TradeService

    tp3_at = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
    tp4_at = datetime(2026, 9, 13, 17, 12, tzinfo=timezone.utc)
    sl_edit = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)
    now = datetime(2026, 9, 13, 19, 4, tzinfo=timezone.utc)

    trade = Trade(
        id=11,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.LIMIT,
        status=TradeStatus.PARTIALLY_CLOSED,
        entry_price=77000.0,
        executed_entry_price=77000.0,
        remaining_percent=70.0,
        opened_at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
        last_monitored_at=datetime(2026, 9, 13, 18, 30, tzinfo=timezone.utc),
        stop_loss=StopLoss(None, 11, 76600.0),
        take_profits=[
            TakeProfitLevel(
                None, 11, i, 77000.0 + i * 100, 10.0,
                status=LevelStatus.TRIGGERED if i <= 3 else LevelStatus.PENDING,
                executed_at=tp3_at if i == 3 else datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc) if i < 3 else None,
            )
            for i in range(1, 6)
        ],
    )

    repo = MagicMock()
    stored = trade
    repo.get_by_id = AsyncMock(side_effect=lambda _id: stored)
    repo.get_events = AsyncMock(return_value=[
        TradeEvent(None, 11, TradeEventType.PARAMS_EDITED, "SL tweak", sl_edit),
    ])
    repo.update = AsyncMock()
    repo.replace_sl = AsyncMock()
    repo.replace_tps = AsyncMock()
    repo.add_event = AsyncMock()
    repo.get_partial_exits = AsyncMock(return_value=[])

    svc = TradeService(repo)
    tp4_candle = Candle(ts=tp4_at, open=77390.0, high=77418.8, low=77390.0, close=77406.4)

    async def fake_fetch(exchange, symbol, since, until=None):
        if since >= sl_edit - timedelta(minutes=2):
            return []
        return [tp4_candle]

    monkeypatch.setattr("bot.services.trade_service.fetch_candles", AsyncMock(side_effect=fake_fetch))
    monkeypatch.setattr("bot.services.trade_service.fetch_price", AsyncMock(return_value=77338.0))

    result = await svc.check_price_triggers(stored, full_replay=True)
    tp4 = next(tp for tp in result.take_profits if tp.order_index == 4)
    assert tp4.status == LevelStatus.TRIGGERED


@pytest.mark.asyncio
async def test_partial_replay_catches_missed_tp_after_downtime(monkeypatch):
    from bot.domain.candles import Candle
    from bot.services.trade_service import TradeService

    tp3_at = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
    tp4_at = datetime(2026, 9, 13, 17, 12, tzinfo=timezone.utc)
    last_monitor = datetime(2026, 9, 13, 16, 5, tzinfo=timezone.utc)
    now = datetime(2026, 9, 13, 19, 4, tzinfo=timezone.utc)

    trade = Trade(
        id=11,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.LIMIT,
        status=TradeStatus.PARTIALLY_CLOSED,
        entry_price=77000.0,
        executed_entry_price=77000.0,
        remaining_percent=70.0,
        opened_at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
        created_at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
        last_monitored_at=last_monitor,
        stop_loss=StopLoss(None, 11, 76600.0),
        take_profits=[
            TakeProfitLevel(
                None, 11, 1, 77100.0, 10.0,
                status=LevelStatus.TRIGGERED,
                executed_at=datetime(2026, 9, 13, 15, 30, tzinfo=timezone.utc),
            ),
            TakeProfitLevel(
                None, 11, 2, 77200.0, 10.0,
                status=LevelStatus.TRIGGERED,
                executed_at=datetime(2026, 9, 13, 15, 45, tzinfo=timezone.utc),
            ),
            TakeProfitLevel(
                None, 11, 3, 77300.0, 10.0,
                status=LevelStatus.TRIGGERED,
                executed_at=tp3_at,
            ),
            TakeProfitLevel(None, 11, 4, 77400.0, 10.0),
            TakeProfitLevel(None, 11, 5, 77500.0, 10.0),
        ],
    )

    repo = MagicMock()
    stored = trade

    async def _save(updated: Trade) -> Trade:
        nonlocal stored
        stored = updated
        return updated

    repo.get_by_id = AsyncMock(side_effect=lambda _id: stored)
    repo.get_events = AsyncMock(return_value=[])
    repo.update = AsyncMock()
    repo.replace_sl = AsyncMock()
    repo.replace_tps = AsyncMock()
    repo.add_event = AsyncMock()
    repo.get_partial_exits = AsyncMock(return_value=[])

    svc = TradeService(repo)
    candles = [
        Candle(ts=tp4_at, open=77390.0, high=77418.8, low=77390.0, close=77406.4),
    ]

    monkeypatch.setattr(
        "bot.services.trade_service.fetch_candles",
        AsyncMock(return_value=candles),
    )
    monkeypatch.setattr(
        "bot.services.trade_service.fetch_price",
        AsyncMock(return_value=77338.0),
    )

    result = await svc.check_price_triggers(stored, full_replay=True)

    assert result.remaining_percent == pytest.approx(60.0)
    tp4 = next(tp for tp in result.take_profits if tp.order_index == 4)
    assert tp4.status == LevelStatus.TRIGGERED
    assert tp4.executed_at == tp4_at


@pytest.mark.asyncio
async def test_market_close_closes_remaining():
    from bot.services.trade_service import TradeService

    trade = Trade(
        id=5,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.PARTIALLY_CLOSED,
        entry_price=77000.0,
        executed_entry_price=77000.0,
        remaining_percent=70.0,
        opened_at=datetime(2026, 9, 13, 12, 0, tzinfo=timezone.utc),
        stop_loss=StopLoss(None, 5, 76600.0),
        take_profits=[
            TakeProfitLevel(
                None, 5, 1, 77100.0, 30.0, status=LevelStatus.TRIGGERED,
                executed_price=77100.0,
            ),
        ],
    )

    repo = MagicMock()
    stored = trade
    repo.get_by_id = AsyncMock(side_effect=lambda _id: stored)
    repo.update = AsyncMock()
    repo.add_event = AsyncMock()
    repo.add_partial_exit = AsyncMock()
    repo.get_partial_exits = AsyncMock(return_value=[])
    repo.replace_tps = AsyncMock()

    closed = Trade(**{**trade.__dict__, "status": TradeStatus.CLOSED, "remaining_percent": 0.0})
    svc = TradeService(repo)
    svc.partial_close = AsyncMock(return_value=closed)

    result = await svc.market_close(trade)
    svc.partial_close.assert_awaited_once_with(trade, 70.0)
    assert result.status == TradeStatus.CLOSED
