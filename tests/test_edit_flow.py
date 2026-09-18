"""Edit trade UI and callback flow tests."""

from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.domain.enums import EntryType, LevelStatus, Side, TradeStatus
from bot.domain.models import StopLoss, TakeProfitLevel, Trade
from bot.handlers.manage import trade_actions
from bot.utils.telegram_ui import CAPTION_MAX_LEN, telegram_html_issues
from bot.utils.trade_setup import format_edit_context


def _trade(**kwargs) -> Trade:
    opened = datetime(2026, 9, 8, 12, 0, tzinfo=timezone.utc)
    defaults = dict(
        id=7,
        user_id=42,
        user_name="Test",
        username="tester",
        exchange="OKX",
        symbol="BTCUSDT",
        side=Side.LONG,
        leverage=10,
        entry_type=EntryType.MARKET,
        status=TradeStatus.PARTIALLY_CLOSED,
        entry_price=78660.8,
        executed_entry_price=78660.8,
        remaining_percent=50.0,
        stop_loss=StopLoss(id=1, trade_id=7, price=78000.0),
        take_profits=[
            TakeProfitLevel(
                id=1, trade_id=7, order_index=1, price=79200.0,
                close_percent=50.0, status=LevelStatus.TRIGGERED,
            ),
            TakeProfitLevel(
                id=2, trade_id=7, order_index=2, price=79800.0,
                close_percent=50.0,
            ),
        ],
        opened_at=opened,
        created_at=opened,
        user_trade_number=5,
    )
    defaults.update(kwargs)
    return Trade(**defaults)


def test_format_edit_context_has_balanced_pre_tags():
    text = format_edit_context(_trade())
    assert "<pre>" in text
    assert "</pre>" in text
    assert telegram_html_issues(text) == []


def test_format_edit_context_does_not_mention_pre_tag_in_prose():
    text = format_edit_context(_trade())
    assert "Tap the <pre>" not in text


def test_format_edit_context_escapes_special_chars_in_template():
    trade = _trade(comment="<test>&")
    text = format_edit_context(trade)
    assert telegram_html_issues(text) == []
    assert "&lt;test&gt;&amp;" in text


def test_edit_context_fits_telegram_caption():
    text = format_edit_context(_trade(comment="x" * 200))
    assert len(text) <= CAPTION_MAX_LEN


def test_edit_context_fits_with_many_take_profits():
    tps = [
        TakeProfitLevel(
            id=i, trade_id=7, order_index=i, price=77000.0 + i * 100,
            close_percent=10.0,
            status=LevelStatus.TRIGGERED if i <= 3 else LevelStatus.PENDING,
        )
        for i in range(1, 11)
    ]
    trade = _trade(take_profits=tps, remaining_percent=70.0)
    text = format_edit_context(trade)
    assert len(text) <= CAPTION_MAX_LEN
    assert telegram_html_issues(text) == []


@pytest.mark.asyncio
async def test_edit_callback_updates_animation_caption():
    trade = _trade()
    container = MagicMock()
    container.trade_repo.get_by_id = AsyncMock(return_value=trade)
    container.trades = MagicMock()
    container.trades.pause_monitoring = MagicMock()
    container.trades.resume_monitoring = MagicMock()

    callback = MagicMock()
    callback.from_user.id = 42
    callback.data = "t:7:edit:all:0"
    callback.message = MagicMock()
    callback.message.chat.id = 100
    callback.message.message_id = 200
    callback.message.message_thread_id = 5
    callback.message.photo = None
    callback.message.animation = MagicMock()
    callback.message.video = None
    callback.message.text = None
    callback.message.caption = "old caption"
    callback.answer = AsyncMock()

    state = MagicMock()
    state.set_state = AsyncMock()
    state.update_data = AsyncMock()
    state.get_data = AsyncMock(return_value={})
    state.clear = AsyncMock()

    effective = MagicMock()
    effective.chat.id = 100
    effective.message_id = 201
    effective.message_thread_id = 5
    container.trade_repo.update = AsyncMock()
    container.profiles.update_card = AsyncMock(return_value=effective)

    with patch("bot.handlers.manage.fetch_price", new=AsyncMock(return_value=79000.0)):
        await trade_actions(callback, state, container)

    container.profiles.update_card.assert_awaited_once()
    prompt_text = container.profiles.update_card.await_args.args[1]
    assert telegram_html_issues(prompt_text) == []
    assert "Edit trade" in prompt_text
    assert "OKX" in prompt_text
    callback.answer.assert_awaited_once()
    state.set_state.assert_awaited_once()
    update_calls = [call.kwargs for call in state.update_data.await_args_list]
    assert any(c.get("trade_id") == 7 for c in update_calls)
    assert any(c.get("card_thread_id") == 5 for c in update_calls)


@pytest.mark.asyncio
async def test_edit_callback_rejects_foreign_trade():
    trade = _trade(user_id=99)
    container = MagicMock()
    container.trade_repo.get_by_id = AsyncMock(return_value=trade)

    callback = MagicMock()
    callback.from_user.id = 42
    callback.data = "t:7:edit:all:0"
    callback.message = MagicMock()
    callback.answer = AsyncMock()

    state = MagicMock()
    with patch("bot.handlers.manage.edit_menu_message", new=AsyncMock()) as edit_mock:
        await trade_actions(callback, state, container)

    edit_mock.assert_not_awaited()
    callback.answer.assert_awaited_once()
    assert callback.answer.await_args.kwargs.get("show_alert") is True
