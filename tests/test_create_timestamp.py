from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.domain.enums import EntryType, Side
from bot.domain.models import ParsedStopLoss, ParsedTrade, TrailMode
from bot.services.trade_service import TradeService


@pytest.mark.asyncio
async def test_create_uses_message_time_not_processing_time(monkeypatch):
    repo = MagicMock()
    repo.create = AsyncMock(side_effect=lambda t: t)
    svc = TradeService(repo)

    sent_at = datetime(2026, 9, 9, 12, 29, tzinfo=timezone.utc)
    processing_at = datetime(2026, 9, 9, 16, 30, tzinfo=timezone.utc)

    monkeypatch.setattr(
        "bot.services.trade_service.validate_leverage",
        AsyncMock(return_value=None),
    )
    monkeypatch.setattr(
        "bot.services.trade_service.fetch_price",
        AsyncMock(return_value=79342.0),
    )
    monkeypatch.setattr(
        "bot.services.trade_service.datetime",
        MagicMock(now=MagicMock(return_value=processing_at)),
    )

    parsed = ParsedTrade(
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        entry_price=None,
        stop_loss=ParsedStopLoss(trail_mode=TrailMode.FIXED, price=79000.0),
        take_profits=[(79500.0, 50.0)],
        comment=None,
    )

    trade = await svc.create_from_parsed(
        user_id=1,
        user_name="Test",
        username=None,
        parsed=parsed,
        recorded_at=sent_at,
    )

    assert trade.created_at == sent_at
    assert trade.opened_at == sent_at
    assert trade.events[0].created_at == sent_at
    assert trade.events[1].created_at == sent_at
