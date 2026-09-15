from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from bot.domain.enums import EntryType, Side, TradeStatus
from bot.domain.models import Trade
from bot.services.trade_service import TradeService


def _svc() -> TradeService:
    return TradeService(MagicMock())


def _trade(**kwargs) -> Trade:
    opened = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    defaults = dict(
        id=7,
        user_id=1,
        user_name="Test",
        username=None,
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.OPEN,
        entry_price=78600.0,
        executed_entry_price=78600.0,
        remaining_percent=100.0,
        opened_at=opened,
        created_at=opened,
        last_monitored_at=datetime(2026, 9, 9, 11, 0, tzinfo=timezone.utc),
    )
    defaults.update(kwargs)
    return Trade(**defaults)


def test_monitor_since_after_downtime_replays_gap():
    svc = _svc()
    trade = _trade()
    now = datetime(2026, 9, 9, 14, 0, tzinfo=timezone.utc)
    since = svc._monitor_since(trade, now)
    assert since == trade.last_monitored_at - timedelta(minutes=1)


def test_monitor_since_deep_replay_when_stuck_at_full_size():
    svc = _svc()
    trade = _trade(last_monitored_at=datetime(2026, 9, 9, 11, 59, tzinfo=timezone.utc))
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    since = svc._monitor_since(trade, now)
    assert since == trade.opened_at


def test_monitor_since_skips_deep_replay_when_partially_closed():
    svc = _svc()
    trade = _trade(remaining_percent=50.0, status=TradeStatus.PARTIALLY_CLOSED)
    now = datetime(2026, 9, 9, 12, 0, tzinfo=timezone.utc)
    since = svc._monitor_since(trade, now)
    assert since == trade.last_monitored_at - timedelta(minutes=1)
