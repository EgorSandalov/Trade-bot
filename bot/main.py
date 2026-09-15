import asyncio
import logging
import sys

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramNetworkError
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

from bot.app.container import AppContainer
from bot.config import BOT_TOKEN, PROXY_URL
from bot.database.context import set_request_chat_id
from bot.database.db import init_db
from bot.domain.enums import TradeStatus
from bot.groups import CONFIGURED_GROUPS
from bot.handlers import commands, create, manage, profile, start
from bot.middleware.access import AccessMiddleware
from bot.middleware.container import ContainerMiddleware
from bot.middleware.db_context import DbContextMiddleware
from bot.utils.formatters import format_trade_card
from bot.utils.telegram_ui import edit_bot_message


async def _update_trade_card(bot: Bot, trade) -> None:
    if not trade.card_chat_id or not trade.card_message_id:
        return
    from bot.keyboards.menus import trade_card_kb

    await edit_bot_message(
        bot,
        trade.card_chat_id,
        trade.card_message_id,
        format_trade_card(trade),
        trade_card_kb(trade.id, trade.status),
    )


async def startup_catch_up(bot: Bot, container: AppContainer) -> None:
    """Replay missed SL/TP from candle history for all open trades."""
    group_ids = list(CONFIGURED_GROUPS) if CONFIGURED_GROUPS else [None]
    for chat_id in group_ids:
        set_request_chat_id(chat_id)
        trades = await container.trade_repo.list_open_trades()
        if not trades:
            continue
        logging.info(
            "Startup catch-up (%s): checking %d open trade(s)",
            chat_id,
            len(trades),
        )
        for trade in trades:
            prev_status = trade.status
            prev_remaining = trade.remaining_percent
            updated = await container.trades.check_price_triggers(trade, full_replay=True)
            changed = (
                updated.status != prev_status
                or abs(updated.remaining_percent - prev_remaining) > 0.01
            )
            if not changed:
                continue
            logging.info(
                "Trade #%s catch-up: %s -> %s, remaining %.0f%%",
                updated.display_number or updated.id,
                prev_status.value,
                updated.status.value,
                updated.remaining_percent,
            )
            if updated.status == TradeStatus.CLOSED and prev_status != TradeStatus.CLOSED:
                await container.notify.notify_trade_closed(bot, updated)
            await _update_trade_card(bot, updated)
    set_request_chat_id(None)


async def price_monitor(bot: Bot, container: AppContainer) -> None:
    group_ids = list(CONFIGURED_GROUPS) if CONFIGURED_GROUPS else [None]
    while True:
        try:
            for chat_id in group_ids:
                set_request_chat_id(chat_id)
                open_trades = await container.trade_repo.list_open_trades()
                if open_trades:
                    logging.debug(
                        "Price monitor (%s): checking %d open trades",
                        chat_id,
                        len(open_trades),
                    )
                for trade in open_trades:
                    prev_status = trade.status
                    prev_remaining = trade.remaining_percent
                    updated = await container.trades.check_price_triggers(trade)
                    changed = (
                        updated.status != prev_status
                        or abs(updated.remaining_percent - prev_remaining) > 0.01
                    )
                    if not changed:
                        continue
                    if updated.status == TradeStatus.CLOSED and prev_status != TradeStatus.CLOSED:
                        await container.notify.notify_trade_closed(bot, updated)
                    await _update_trade_card(bot, updated)
        except Exception:
            logging.exception("Price monitor error")
        finally:
            set_request_chat_id(None)
        await asyncio.sleep(7)


async def setup_bot_commands(bot: Bot) -> None:
    try:
        await bot.set_my_commands([
            BotCommand(command="faq", description="FAQ"),
            BotCommand(command="trades", description="My trades"),
            BotCommand(command="leaderboard", description="Rankings"),
            BotCommand(command="myprofile", description="Banner + epic stickers (+100% / -100%)"),
            BotCommand(command="help", description="Quick reference"),
            BotCommand(command="chat_id", description="Group & topic IDs"),
            BotCommand(command="myid", description="Your Telegram ID"),
        ])
    except TelegramNetworkError:
        logging.warning("Could not register bot commands (network/proxy issue)")


def _build_bot() -> Bot:
    session = AiohttpSession(proxy=PROXY_URL) if PROXY_URL else None
    return Bot(
        token=BOT_TOKEN,
        session=session,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )


async def _check_telegram_connection(bot: Bot) -> None:
    try:
        me = await bot.get_me()
        logging.info("Connected as @%s (id %s)", me.username, me.id)
    except TelegramNetworkError as e:
        if PROXY_URL:
            print(
                f"\nCannot reach Telegram API via proxy:\n  {PROXY_URL}\n\n"
                "The proxy is not running or the address is wrong.\n"
                "• Start your VPN/proxy client, or\n"
                "• Remove PROXY_URL from .env (or leave it empty) if Telegram works directly.\n"
                f"\nDetails: {e}\n"
            )
        else:
            print(
                "\nCannot reach Telegram API.\n"
                "Check internet connection or set PROXY_URL in .env if Telegram is blocked.\n"
                f"\nDetails: {e}\n"
            )
        await bot.session.close()
        sys.exit(1)


async def main() -> None:
    if not BOT_TOKEN:
        print("Set BOT_TOKEN in .env file (see .env.example)")
        sys.exit(1)

    logging.basicConfig(level=logging.INFO)
    await init_db()

    container = AppContainer.create_default()
    group_ids = list(CONFIGURED_GROUPS) if CONFIGURED_GROUPS else [None]
    for chat_id in group_ids:
        set_request_chat_id(chat_id)
        n = await container.trade_repo.recalc_all_closed_trades()
        if n:
            logging.info("Recalculated %d closed trades in group %s", n, chat_id)
    set_request_chat_id(None)

    bot = _build_bot()
    await _check_telegram_connection(bot)

    dp = Dispatcher(storage=MemoryStorage())
    dp.message.middleware(AccessMiddleware())
    dp.callback_query.middleware(AccessMiddleware())
    dp.message.middleware(DbContextMiddleware())
    dp.callback_query.middleware(DbContextMiddleware())
    dp.message.middleware(ContainerMiddleware(container))
    dp.callback_query.middleware(ContainerMiddleware(container))

    dp.include_router(start.router)
    dp.include_router(commands.router)
    dp.include_router(manage.router)
    dp.include_router(profile.router)
    dp.include_router(create.router)

    await setup_bot_commands(bot)
    await startup_catch_up(bot, container)
    asyncio.create_task(price_monitor(bot, container))
    await dp.start_polling(bot, allowed_updates=["message", "callback_query"])


if __name__ == "__main__":
    asyncio.run(main())
