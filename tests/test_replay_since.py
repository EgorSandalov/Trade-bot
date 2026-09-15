from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.domain.enums import (
    EntryType,
    LevelStatus,
    Side,
    TradeEventType,
    TradeStatus,
    TrailMode,
)
from bot.domain.models import StopLoss, TakeProfitLevel, Trade, TradeEvent
from bot.services.trade_service import TradeService, _levels_anchor


def _svc() -> TradeService:
    return TradeService(MagicMock())


def _trade(**kwargs) -> Trade:
    opened = datetime(2026, 9, 8, 15, 45, tzinfo=timezone.utc)
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
        status=TradeStatus.PARTIALLY_CLOSED,
        entry_price=78660.0,
        executed_entry_price=78660.0,
        remaining_percent=50.0,
        opened_at=opened,
        created_at=opened,
        last_monitored_at=datetime(2026, 9, 9, 11, 0, tzinfo=timezone.utc),
        take_profits=[
            TakeProfitLevel(
                None, 5, 1, 79200.0, 50.0,
                status=LevelStatus.TRIGGERED,
                executed_at=datetime(2026, 9, 9, 11, 42, tzinfo=timezone.utc),
            ),
            TakeProfitLevel(None, 5, 2, 79500.0, 50.0),
        ],
        stop_loss=StopLoss(None, 5, 78600.0),
    )
    defaults.update(kwargs)
    return Trade(**defaults)


def test_levels_anchor_uses_latest_tp_and_edit():
    trade = _trade()
    sl_edit = datetime(2026, 9, 9, 12, 31, tzinfo=timezone.utc)
    events = [
        TradeEvent(None, 5, TradeEventType.TP_TRIGGERED, "TP1", trade.take_profits[0].executed_at),
        TradeEvent(None, 5, TradeEventType.PARAMS_EDITED, "SL: 78000 → 78600", sl_edit),
    ]
    anchor = _levels_anchor(trade, events)
    assert anchor == sl_edit


def test_replay_since_full_replay_starts_after_sl_edit():
    svc = _svc()
    trade = _trade(
        status=TradeStatus.OPEN,
        remaining_percent=100.0,
        last_monitored_at=None,
        take_profits=[TakeProfitLevel(None, 5, 2, 79500.0, 50.0)],
    )
    sl_edit = datetime(2026, 9, 9, 12, 31, tzinfo=timezone.utc)
    events = [
        TradeEvent(None, 5, TradeEventType.PARAMS_EDITED, "SL edit", sl_edit),
    ]
    now = datetime(2026, 9, 9, 13, 15, tzinfo=timezone.utc)
    since = svc._replay_since(trade, now, full_replay=True, events=events)
    assert since == sl_edit - timedelta(minutes=1)


def test_replay_since_incremental_respects_sl_edit_after_downtime():
    svc = _svc()
    trade = _trade()
    sl_edit = datetime(2026, 9, 9, 12, 31, tzinfo=timezone.utc)
    events = [
        TradeEvent(None, 5, TradeEventType.PARAMS_EDITED, "SL edit", sl_edit),
    ]
    now = datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc)
    since = svc._replay_since(trade, now, full_replay=False, events=events)
    assert since >= sl_edit - timedelta(minutes=1)


def test_replay_since_partial_after_downtime_uses_last_monitored():
    svc = _svc()
    opened = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    tp3_at = datetime(2026, 9, 13, 16, 0, tzinfo=timezone.utc)
    last_monitor = datetime(2026, 9, 13, 16, 5, tzinfo=timezone.utc)
    sl_edit = datetime(2026, 9, 13, 18, 0, tzinfo=timezone.utc)
    trade = _trade(
        opened_at=opened,
        last_monitored_at=last_monitor,
        take_profits=[
            TakeProfitLevel(
                None, 5, 1, 79200.0, 10.0,
                status=LevelStatus.TRIGGERED,
                executed_at=datetime(2026, 9, 13, 15, 0, tzinfo=timezone.utc),
            ),
            TakeProfitLevel(
                None, 5, 2, 79300.0, 10.0,
                status=LevelStatus.TRIGGERED,
                executed_at=datetime(2026, 9, 13, 15, 30, tzinfo=timezone.utc),
            ),
            TakeProfitLevel(
                None, 5, 3, 79400.0, 10.0,
                status=LevelStatus.TRIGGERED,
                executed_at=tp3_at,
            ),
            TakeProfitLevel(None, 5, 4, 79500.0, 10.0),
        ],
        remaining_percent=60.0,
    )
    events = [
        TradeEvent(None, 5, TradeEventType.PARAMS_EDITED, "SL edit", sl_edit),
    ]
    now = datetime(2026, 9, 13, 19, 4, tzinfo=timezone.utc)
    since = svc._replay_since(trade, now, full_replay=True, events=events)
    assert since <= last_monitor


def test_replay_since_open_trade_still_from_open():
    svc = _svc()
    opened = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    trade = _trade(
        status=TradeStatus.OPEN,
        remaining_percent=100.0,
        opened_at=opened,
        take_profits=[TakeProfitLevel(None, 5, 1, 79500.0, 50.0)],
        last_monitored_at=None,
    )
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    since = svc._replay_since(trade, now, full_replay=True, events=[])
    assert since == opened
