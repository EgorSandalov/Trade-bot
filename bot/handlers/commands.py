from aiogram import F, Router
from aiogram.filters import Command
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.app.container import AppContainer
from bot.domain.enums import Period, period_label
from bot.handlers.common import require_general
from bot.handlers.trade_flow import end_trade_flow
from bot.keyboards.menus import (
    leaderboard_traders_kb,
    my_trades_kb,
    paginate_leaderboard,
    paginate_trader_trades,
    paginate_my_trades,
    trade_detail_kb,
    trader_detail_kb,
)
from bot.utils.formatters import format_leaderboard, format_trade_detail, format_trader_stats
from bot.utils.links import setup_message_link
from bot.utils.telegram_ui import answer_if_unchanged

router = Router()


async def _my_trades_content(container: AppContainer, user_id: int, period: Period, page: int = 0):
    text, trades, page, kb = await container.trades_view.build_my_trades_view(user_id, period, page)
    _, page, total_pages = paginate_my_trades(trades, page)
    return text, trades, page, total_pages, kb


async def _show_my_trades_callback(
    callback: CallbackQuery,
    container: AppContainer,
    user_id: int,
    period: Period,
    page: int = 0,
) -> None:
    if not callback.message:
        return
    text, trades, page, _total_pages, kb = await _my_trades_content(container, user_id, period, page)
    if await answer_if_unchanged(callback, text, kb):
        return
    await container.profiles.update_card(callback.message, text, kb, user_id=user_id)
    await callback.answer()


def _parse_my_trades_callback(data: str) -> tuple[Period, int]:
    parts = data.split(":")
    period = Period(parts[1])
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return period, page


@router.message(Command("trades"))
async def my_trades(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user or not await require_general(message, container.access):
        return
    await end_trade_flow(state, container.trades)
    user_id = message.from_user.id
    period = Period.ALL
    text, trades, page, _total_pages, kb = await _my_trades_content(container, user_id, period, 0)
    await container.profiles.send_card(message, text, kb, user_id=user_id)


@router.callback_query(F.data.startswith("mt:"))
async def my_trades_nav(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if not callback.from_user or not callback.message:
        return
    if callback.data == "mt:noop":
        await callback.answer()
        return
    await end_trade_flow(state, container.trades)
    period, page = _parse_my_trades_callback(callback.data)
    await _show_my_trades_callback(callback, container, callback.from_user.id, period, page)


def _parse_leaderboard_callback(data: str) -> tuple[Period, int]:
    parts = data.split(":")
    if len(parts) > 2 and parts[1] == "noop":
        raise ValueError("noop")
    period = Period(parts[1])
    page = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    return period, page


async def _show_leaderboard(callback: CallbackQuery, container: AppContainer, period: Period, page: int = 0) -> None:
    if not callback.message:
        return
    label = period_label(period)
    entries = await container.stats_repo.get_leaderboard(period)
    page_entries, page, total_pages = paginate_leaderboard(entries, period, page)
    text = format_leaderboard(page_entries, label, page=page, total_pages=total_pages)
    kb = leaderboard_traders_kb(entries, period, page=page)
    if await answer_if_unchanged(callback, text, kb):
        return
    await container.profiles.update_card(
        callback.message,
        text,
        kb,
        photo_path=container.profiles.group_banner(),
    )
    await callback.answer()


@router.message(Command("leaderboard"))
async def leaderboard_cmd(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not await require_general(message, container.access):
        return
    await end_trade_flow(state, container.trades)
    period = Period.MONTH
    label = period_label(period)
    entries = await container.stats_repo.get_leaderboard(period)
    page_entries, page, total_pages = paginate_leaderboard(entries, period, 0)
    await container.profiles.send_card(
        message,
        format_leaderboard(page_entries, label, page=page, total_pages=total_pages),
        leaderboard_traders_kb(entries, period, page=page),
        photo_path=container.profiles.group_banner(),
    )


@router.callback_query(F.data.startswith("lb:"))
async def leaderboard_period(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if not callback.message or not callback.from_user:
        return
    if callback.data == "lb:noop":
        await callback.answer()
        return
    try:
        period, page = _parse_leaderboard_callback(callback.data)
    except ValueError:
        await callback.answer()
        return
    await end_trade_flow(state, container.trades)
    await _show_leaderboard(callback, container, period, page)


@router.callback_query(F.data.startswith("lp:"))
async def leaderboard_profile_only(callback: CallbackQuery) -> None:
    await callback.answer(
        "Profile is set up — no closed trades yet. "
        "Once the first trade closes, they join the ranking.",
        show_alert=True,
    )


def _parse_trader_callback(data: str) -> tuple[int, Period, int]:
    parts = data.split(":")
    user_id = int(parts[1])
    period = Period(parts[2])
    page = int(parts[3]) if len(parts) > 3 and parts[3].isdigit() else 0
    return user_id, period, page


@router.callback_query(F.data.startswith("tr:"))
async def trader_detail(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if not callback.message:
        return
    if callback.data == "tr:noop":
        await callback.answer()
        return
    await end_trade_flow(state, container.trades)
    user_id, period, page = _parse_trader_callback(callback.data)
    label = period_label(period)
    stats = await container.stats_repo.get_trader_stats(user_id, period)
    if not stats:
        await callback.answer("No data", show_alert=True)
        return

    trades = await container.stats_repo.get_trader_closed_trades(user_id, period)
    _, page, total_pages = paginate_trader_trades(trades, page)
    if total_pages > 1:
        label += f" ({page + 1}/{total_pages})"
    text = format_trader_stats(stats, label)
    if trades:
        text += "\n\n<i>Tap a trade below</i>"
    kb = trader_detail_kb(user_id, period, trades, page=page)
    if await answer_if_unchanged(callback, text, kb):
        return
    await container.profiles.update_card(callback.message, text, kb, user_id=user_id)
    await callback.answer()


@router.callback_query(F.data.startswith("tt:"))
async def trade_detail(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if not callback.message:
        return
    await end_trade_flow(state, container.trades)
    parts = callback.data.split(":")
    trade_id = int(parts[1])
    user_id = int(parts[2])
    period = Period(parts[3])
    page = int(parts[4]) if len(parts) > 4 and parts[4].isdigit() else 0

    trade = await container.trade_repo.get_by_id(trade_id)
    if not trade or trade.user_id != user_id:
        await callback.answer("Trade not found", show_alert=True)
        return

    events = await container.trade_repo.get_events(trade_id)
    trades = await container.stats_repo.get_trader_closed_trades(user_id, period)
    setup_url = None
    chat_id = trade.setup_chat_id or trade.card_chat_id
    if trade.setup_message_id and chat_id:
        setup_url = setup_message_link(
            chat_id, trade.setup_thread_id, trade.setup_message_id,
        )

    await container.profiles.update_card(
        callback.message,
        format_trade_detail(trade, events),
        trade_detail_kb(trade_id, user_id, period, setup_url, trades=trades, page=page),
        user_id=user_id,
    )
    await callback.answer()
