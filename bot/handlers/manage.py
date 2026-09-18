import logging

from aiogram import F, Router
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.app.container import AppContainer
from bot.domain.enums import Period, TradeStatus
from bot.domain.models import Trade
from bot.filters.general_topic import InGeneralOrPrivateFilter
from bot.handlers.common import require_general
from bot.handlers.states import CancelStates, EditStates
from bot.handlers.trade_flow import begin_trade_flow, end_trade_flow
from bot.keyboards.menus import (
    cancel_prompt_kb,
    edit_prompt_kb,
    history_back_kb,
    market_close_prompt_kb,
    my_trade_active_kb,
    my_trade_detail_kb,
    parse_trade_ctx,
    trade_card_kb,
)
from bot.services.price_service import fetch_price
from bot.utils.formatters import format_history, format_trade_card, format_trade_detail
from bot.utils.links import setup_message_link
from bot.utils.telegram_ui import delete_message, edit_bot_message, edit_menu_message, looks_like_setup_edit
from bot.utils.trade_setup import format_edit_context

router = Router()
log = logging.getLogger(__name__)


def _parse_trade_callback(data: str) -> tuple[int, str, str | None, int]:
    parts = data.split(":")
    trade_id = int(parts[1])
    action = parts[2]
    if len(parts) > 4 and parts[4].isdigit():
        return trade_id, action, parts[3], int(parts[4])
    ctx = parts[3] if len(parts) > 3 and parts[3] else None
    period, page = parse_trade_ctx(ctx)
    return trade_id, action, period, page


async def _owner_check(callback: CallbackQuery, trade) -> bool:
    if not trade or trade.user_id != callback.from_user.id:
        await callback.answer("Not your trade", show_alert=True)
        return False
    return True


async def _save_card(container: AppContainer, trade_id: int, chat_id: int, message_id: int) -> None:
    trade = await container.trade_repo.get_by_id(trade_id)
    if trade:
        trade.card_chat_id = chat_id
        trade.card_message_id = message_id
        await container.trade_repo.update(trade)


async def _my_trades_for_nav(container: AppContainer, user_id: int, period: str) -> list:
    return await container.trade_repo.list_user_trades_for_period(user_id, Period(period))


async def _on_closed(container: AppContainer, bot, trade) -> None:
    if trade.status == TradeStatus.CLOSED:
        await container.notify.notify_trade_closed(bot, trade)


async def _sync_trade(
    container: AppContainer,
    bot,
    trade,
    *,
    prev_status: TradeStatus | None = None,
    full_replay: bool = False,
) -> tuple[Trade, TradeStatus]:
    prev = prev_status if prev_status is not None else trade.status
    updated = await container.trades.check_price_triggers(trade, full_replay=full_replay)
    if updated.status == TradeStatus.CLOSED and prev != TradeStatus.CLOSED:
        await _on_closed(container, bot, updated)
    return updated, prev


async def _edit_card(
    container: AppContainer,
    bot,
    chat_id: int,
    message_id: int,
    trade,
    period: str | None,
    page: int = 0,
    *,
    suffix: str = "",
    reply_markup=None,
    message: Message | None = None,
) -> None:
    events = await container.trade_repo.get_events(trade.id)
    price = await fetch_price(trade.exchange, trade.symbol)
    text = format_trade_card(trade, price, events=events)
    if suffix:
        text += suffix
    kb = reply_markup or trade_card_kb(trade.id, trade.status, period, page)
    if message:
        await edit_menu_message(message, text, kb)
        return
    await edit_bot_message(bot, chat_id, message_id, text, kb)


def _trade_locked(trade) -> bool:
    return trade.status in (TradeStatus.CLOSED, TradeStatus.CANCELLED)


async def _edit_my_trade_view(
    container: AppContainer,
    bot,
    chat_id: int,
    message_id: int,
    trade,
    period: str,
    page: int,
    *,
    message: Message | None = None,
    message_thread_id: int | None = None,
    trades: list | None = None,
) -> Message | None:
    events = await container.trade_repo.get_events(trade.id)
    setup_url = _setup_url(trade)
    nav_trades = trades
    if nav_trades is None and trade.user_id is not None:
        nav_trades = await _my_trades_for_nav(container, trade.user_id, period)
    if trade.status in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
        text = format_trade_detail(trade, events)
        kb = my_trade_detail_kb(
            trade.id, period, page, setup_url,
            show_history=trade.status == TradeStatus.CLOSED,
            trades=nav_trades,
        )
    else:
        price = await fetch_price(trade.exchange, trade.symbol)
        text = format_trade_card(trade, price, events=events)
        kb = my_trade_active_kb(trade.id, period, page, setup_url, trades=nav_trades)
    if message:
        return await edit_menu_message(message, text, kb)
    return await edit_bot_message(
        bot, chat_id, message_id, text, kb,
        message_thread_id=message_thread_id,
        anchor_message=message,
    )


def _setup_url(trade: Trade) -> str | None:
    chat_id = trade.setup_chat_id or trade.card_chat_id
    if trade.setup_message_id and chat_id:
        return setup_message_link(
            chat_id, trade.setup_thread_id, trade.setup_message_id,
        )
    return None


async def _show_my_trade_view(
    container: AppContainer,
    message: Message,
    trade,
    period: str,
    page: int,
    *,
    trades: list | None = None,
) -> Message:
    events = await container.trade_repo.get_events(trade.id)
    setup_url = _setup_url(trade)
    nav_trades = trades
    if nav_trades is None and trade.user_id is not None:
        nav_trades = await _my_trades_for_nav(container, trade.user_id, period)
    if trade.status in (TradeStatus.CLOSED, TradeStatus.CANCELLED):
        text = format_trade_detail(trade, events)
        kb = my_trade_detail_kb(
            trade.id, period, page, setup_url,
            show_history=trade.status == TradeStatus.CLOSED,
            trades=nav_trades,
        )
    else:
        price = await fetch_price(trade.exchange, trade.symbol)
        text = format_trade_card(trade, price, events=events)
        kb = my_trade_active_kb(trade.id, period, page, setup_url, trades=nav_trades)
    return await edit_menu_message(message, text, kb)


def _state_trade_ctx(data: dict) -> tuple[str, int]:
    period = data.get("period") or data.get("list_type") or Period.ALL.value
    if period in ("active", "closed"):
        period = Period.ALL.value
    page = int(data.get("page", 0))
    return period, page


async def _show_my_trades_list(
    callback: CallbackQuery,
    container: AppContainer,
    user_id: int,
    period: Period,
    page: int = 0,
    *,
    note: str = "",
) -> None:
    if not callback.message:
        return
    text, _items, page, kb = await container.trades_view.build_my_trades_view(
        user_id, period, page, note=note,
    )
    await edit_menu_message(callback.message, text, kb)


@router.callback_query(F.data.startswith("t:"))
async def trade_actions(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if not callback.message:
        return
    trade_id, action, period, page = _parse_trade_callback(callback.data)

    trade = await container.trade_repo.get_by_id(trade_id)
    if not await _owner_check(callback, trade):
        return

    prev_status = trade.status
    period = period or Period.ALL.value

    if action in ("refresh", "open", "chart"):
        await end_trade_flow(state, container.trades)
        trade, prev_status = await _sync_trade(
            container,
            callback.bot,
            trade,
            prev_status=prev_status,
            full_replay=(action == "refresh"),
        )
        nav_trades = await _my_trades_for_nav(container, callback.from_user.id, period)
        effective = await _show_my_trade_view(
            container, callback.message, trade, period, page, trades=nav_trades,
        )
        if action == "open":
            await _save_card(
                container, trade_id, effective.chat.id, effective.message_id,
            )
        await callback.answer("Updated" if action == "refresh" else "")
        return

    if action == "edit":
        try:
            if _trade_locked(trade):
                await end_trade_flow(state, container.trades)
                await _show_my_trade_view(container, callback.message, trade, period, page)
                alert = "Trade already cancelled" if trade.status == TradeStatus.CANCELLED else "Trade already closed"
                await callback.answer(alert, show_alert=True)
                return

            await begin_trade_flow(state, container.trades, trade_id)
            await state.set_state(EditStates.waiting_setup)
            await state.update_data(
                trade_id=trade_id,
                period=period,
                page=page,
                card_chat_id=callback.message.chat.id,
                card_message_id=callback.message.message_id,
                card_thread_id=callback.message.message_thread_id,
            )
            effective = await edit_menu_message(
                callback.message,
                format_edit_context(trade),
                edit_prompt_kb(trade_id, period, page),
            )
            await state.update_data(
                card_chat_id=effective.chat.id,
                card_message_id=effective.message_id,
                card_thread_id=effective.message_thread_id,
            )
            await _save_card(container, trade_id, effective.chat.id, effective.message_id)
            await callback.answer()
        except Exception:
            log.exception("Edit flow failed for trade %s", trade_id)
            await end_trade_flow(state, container.trades)
            await callback.answer("Could not open edit — try again", show_alert=True)
        return

    if action == "ask_market":
        if _trade_locked(trade):
            await end_trade_flow(state, container.trades)
            await _show_my_trade_view(container, callback.message, trade, period, page)
            alert = "Trade already cancelled" if trade.status == TradeStatus.CANCELLED else "Trade already closed"
            await callback.answer(alert, show_alert=True)
            return

        await begin_trade_flow(state, container.trades, trade_id)
        await state.update_data(trade_id=trade_id, period=period, page=page)
        price = await fetch_price(trade.exchange, trade.symbol)
        text = (
            format_trade_card(trade, price)
            + "\n\n📤 <b>Close at market</b>\n"
            f"Close the remaining <b>{trade.remaining_percent:.0f}%</b> at the current "
            f"market price ({trade.exchange}).\n"
            "Tap ✅ Close now to confirm or ◀ Back to return.\n\n"
            "⏸ SL/TP monitoring is <b>paused</b> until you finish or tap Back."
        )
        effective = await edit_menu_message(
            callback.message,
            text,
            market_close_prompt_kb(trade_id, period, page),
        )
        await state.update_data(
            trade_id=trade_id,
            period=period,
            page=page,
            card_chat_id=effective.chat.id,
            card_message_id=effective.message_id,
            card_thread_id=effective.message_thread_id,
        )
        await callback.answer()
        return

    if action == "market_confirm":
        if _trade_locked(trade):
            await end_trade_flow(state, container.trades)
            await _show_my_trade_view(container, callback.message, trade, period, page)
            alert = "Trade already cancelled" if trade.status == TradeStatus.CANCELLED else "Trade already closed"
            await callback.answer(alert, show_alert=True)
            return

        try:
            trade = await container.trades.market_close(trade)
        except ValueError as exc:
            await callback.answer(str(exc), show_alert=True)
            return

        await end_trade_flow(state, container.trades)
        if trade.status == TradeStatus.CLOSED:
            await _on_closed(container, callback.bot, trade)
        nav_trades = await _my_trades_for_nav(container, callback.from_user.id, period)
        effective = await _show_my_trade_view(
            container, callback.message, trade, period, page, trades=nav_trades,
        )
        await _save_card(container, trade_id, effective.chat.id, effective.message_id)
        await callback.answer("Position closed at market")
        return

    if action == "ask_cancel":
        if _trade_locked(trade):
            await end_trade_flow(state, container.trades)
            await _show_my_trade_view(container, callback.message, trade, period, page)
            alert = "Trade already cancelled" if trade.status == TradeStatus.CANCELLED else "Trade already closed"
            await callback.answer(alert, show_alert=True)
            return

        await begin_trade_flow(state, container.trades, trade_id)
        await state.set_state(CancelStates.waiting_reason)
        await state.update_data(
            trade_id=trade_id,
            period=period,
            page=page,
            card_chat_id=callback.message.chat.id,
            card_message_id=callback.message.message_id,
            card_thread_id=callback.message.message_thread_id,
        )
        price = await fetch_price(trade.exchange, trade.symbol)
        text = (
            format_trade_card(trade, price)
            + "\n\n❌ <b>Cancel trade</b>\n"
            "Send a reason (message) or tap Skip.\n"
            "Tap ◀ Back to return without cancelling.\n\n"
            "⏸ SL/TP monitoring is <b>paused</b> until you finish or tap Back."
        )
        await edit_menu_message(
            callback.message,
            text,
            cancel_prompt_kb(trade_id, period, page),
        )
        await callback.answer()
        return

    if action == "cancel_skip":
        await end_trade_flow(state, container.trades)
        trade = await container.trade_repo.get_by_id(trade_id)
        if not trade or _trade_locked(trade):
            if trade:
                await _show_my_trade_view(container, callback.message, trade, period, page)
            alert = "Trade already cancelled" if trade and trade.status == TradeStatus.CANCELLED else "Trade already closed"
            await callback.answer(alert, show_alert=True)
            return

        await container.trades.cancel_trade(trade)
        await _show_my_trades_list(
            callback,
            container,
            callback.from_user.id,
            Period(period),
            page,
            note="<i>Trade cancelled.</i>",
        )
        await callback.answer("Cancelled")
        return

    if action == "history":
        await end_trade_flow(state, container.trades)
        events = await container.trade_repo.get_events(trade_id)
        await edit_menu_message(
            callback.message,
            format_history(events, trade.display_number),
            history_back_kb(trade_id, period, page),
        )
        await callback.answer()
        return


@router.message(EditStates.waiting_setup, InGeneralOrPrivateFilter())
async def edit_setup(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user:
        return
    if not await require_general(message, container.access):
        return

    data = await state.get_data()
    trade_id = data["trade_id"]
    period, page = _state_trade_ctx(data)
    card_chat_id = data.get("card_chat_id")
    card_message_id = data.get("card_message_id")
    card_thread_id = data.get("card_thread_id")
    trade = await container.trade_repo.get_by_id(trade_id)

    if not trade or trade.user_id != message.from_user.id:
        await end_trade_flow(state, container.trades)
        await message.reply("⚠️ Trade not found — tap ◀ Back and open Edit again.")
        return

    try:
        price = await fetch_price(trade.exchange, trade.symbol)
    except Exception:
        log.exception("Price fetch failed during edit for trade %s", trade_id)
        await message.reply("⚠️ Could not fetch market price — try again.")
        return

    async def _update_edit_card(extra: str) -> None:
        text = format_edit_context(trade) + extra
        kb = edit_prompt_kb(trade_id, period, page)
        if card_chat_id and card_message_id:
            fallback = await edit_bot_message(
                message.bot,
                card_chat_id,
                card_message_id,
                text,
                kb,
                message_thread_id=card_thread_id,
                anchor_message=message,
            )
            if fallback is not None:
                await state.update_data(
                    card_chat_id=fallback.chat.id,
                    card_message_id=fallback.message_id,
                    card_thread_id=fallback.message_thread_id,
                )
                await _save_card(container, trade_id, fallback.chat.id, fallback.message_id)
            return
        await message.answer(text, reply_markup=kb, parse_mode="HTML")

    if not message.text:
        await _update_edit_card("\n\n⚠️ <i>Send the edited setup as text (copy the template above).</i>")
        return

    if message.text.startswith("/"):
        return

    if not looks_like_setup_edit(message.text):
        await _update_edit_card(
            "\n\n⚠️ <i>Send the full setup template (multiple lines), not a single line or command.</i>"
        )
        return

    try:
        trade = await container.trades.apply_trade_edit(trade, message.text, price)
    except ValueError as e:
        if looks_like_setup_edit(message.text):
            await delete_message(message)
        err_text = str(e).replace("\n", "\n• ")
        await _update_edit_card(f"\n\n⚠️ <i>{err_text}</i>")
        return
    except Exception:
        log.exception("apply_trade_edit failed for trade %s", trade_id)
        await _update_edit_card(
            "\n\n⚠️ <i>Could not save changes — check the template and try again.</i>"
        )
        return

    await delete_message(message)
    await end_trade_flow(state, container.trades)
    trade, _ = await _sync_trade(container, message.bot, trade)

    nav_trades = await _my_trades_for_nav(container, message.from_user.id, period)
    if card_chat_id and card_message_id:
        fallback = await _edit_my_trade_view(
            container, message.bot, card_chat_id, card_message_id, trade, period, page,
            message=message,
            message_thread_id=card_thread_id,
            trades=nav_trades,
        )
        if fallback is not None:
            await _save_card(container, trade_id, fallback.chat.id, fallback.message_id)
    else:
        await message.answer(
            format_trade_card(trade, price),
            reply_markup=my_trade_active_kb(
                trade_id, period, page, _setup_url(trade), trades=nav_trades,
            ),
            parse_mode="HTML",
        )


@router.message(CancelStates.waiting_reason, InGeneralOrPrivateFilter())
async def cancel_reason(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user or not message.text:
        return
    if message.text.startswith("/"):
        return
    if not await require_general(message, container.access):
        return

    data = await state.get_data()
    trade_id = data["trade_id"]
    period, page = _state_trade_ctx(data)
    card_chat_id = data.get("card_chat_id")
    card_message_id = data.get("card_message_id")

    trade = await container.trade_repo.get_by_id(trade_id)
    if not trade or trade.user_id != message.from_user.id:
        await end_trade_flow(state, container.trades)
        return

    reason = message.text.strip()
    await delete_message(message)
    await end_trade_flow(state, container.trades)
    await container.trades.cancel_trade(trade, reason)

    if card_chat_id and card_message_id:
        text, _, page, kb = await container.trades_view.build_my_trades_view(
            message.from_user.id,
            Period(period),
            page,
            note="<i>Trade cancelled.</i>",
        )
        await edit_bot_message(
            message.bot,
            card_chat_id,
            card_message_id,
            text,
            kb,
        )
