import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock

import pytest

from bot.domain.enums import EntryType, Side, TradeStatus
from bot.domain.models import Trade
from bot.services.notify_service import NotifyService


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


def _closed_trade(*, personal: float) -> Trade:
    return Trade(
        id=1,
        user_id=42,
        user_name="Trader",
        username="trader",
        exchange="OKX",
        symbol="BTC-USDT-SWAP",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.CLOSED,
        entry_price=70000.0,
        executed_entry_price=70000.0,
        result_personal_move_pct=personal,
        setup_chat_id=-123,
        setup_message_id=100,
        setup_thread_id=200,
        closed_at=datetime.now(timezone.utc),
    )


@pytest.mark.asyncio
async def test_notify_sends_win_sticker_on_plus_100(monkeypatch):
    profiles = MagicMock()
    profiles.get_reaction_media = AsyncMock(return_value=("win_fid", "sticker"))
    profiles.get_loss_reaction_media = AsyncMock(return_value=None)
    bot = AsyncMock()
    svc = NotifyService(profiles)

    await svc.notify_trade_closed(bot, _closed_trade(personal=120.0))

    bot.send_sticker.assert_awaited_once()
    bot.send_animation.assert_not_awaited()
    profiles.get_reaction_media.assert_awaited_once_with(42)
    profiles.get_loss_reaction_media.assert_not_awaited()


@pytest.mark.asyncio
async def test_notify_sends_loss_sticker_on_minus_100(monkeypatch):
    profiles = MagicMock()
    profiles.get_reaction_media = AsyncMock(return_value=None)
    profiles.get_loss_reaction_media = AsyncMock(return_value=("loss_fid", "animation"))
    bot = AsyncMock()
    svc = NotifyService(profiles)

    await svc.notify_trade_closed(bot, _closed_trade(personal=-150.0))

    bot.send_animation.assert_awaited_once()
    bot.send_sticker.assert_not_awaited()
    profiles.get_loss_reaction_media.assert_awaited_once_with(42)
    profiles.get_reaction_media.assert_not_awaited()
