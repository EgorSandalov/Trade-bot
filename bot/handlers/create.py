import logging

from aiogram import F, Router
from aiogram.filters import StateFilter
from aiogram.types import Message

from bot.app.container import AppContainer
from bot.domain.enums import TradeStatus
from bot.domain.exchanges import exchanges_list, is_supported_exchange, normalize_exchange
from bot.domain.parser import looks_like_setup, parse_trade_message
from bot.domain.results import Failure
from bot.handlers.states import CancelStates, EditStates, ProfileStates
from bot.services.access_service import AccessService

router = Router()
log = logging.getLogger(__name__)

def _setup_text(message: Message) -> str | None:
    text = message.text or message.caption
    if not text:
        return None
    text = text.strip()
    if not text or text.startswith("/"):
        return None
    return text


@router.message(
    (F.text & ~F.text.startswith("/")) | F.photo | F.document | F.video | F.animation,
    ~StateFilter(EditStates, CancelStates, ProfileStates),
)
async def handle_setup_message(message: Message, container: AppContainer) -> None:
    if not message.from_user:
        return

    body = _setup_text(message)
    if not body or "\n" not in body:
        return

    access: AccessService = container.access
    if access.is_private_chat(message.chat.id):
        if looks_like_setup(body):
            await message.reply(
                "⚠️ Setups can only be posted in the group <b>Setups</b> topic — not in DMs."
            )
        return
    if not await access.can_create_setup(
        message.bot, message.from_user.id, message.chat.id, message.message_thread_id
    ):
        if looks_like_setup(body):
            await message.reply("⚠️ Setups can only be posted in the Setups topic.")
        return

    first_line = normalize_exchange(body.splitlines()[0].strip())
    if not is_supported_exchange(first_line):
        if looks_like_setup(body):
            hint = exchanges_list()
            if body.splitlines()[0].strip().upper() in ("LONG", "SHORT"):
                await message.reply(
                    "❌ <b>Missing exchange</b> — first line must be the exchange, then pair.\n\n"
                    f"<pre>OKX\nBTC\nLONG\n...</pre>\n\n"
                    f"Supported: {hint}",
                )
            else:
                await message.reply(
                    f"❌ Unknown exchange: <b>{body.splitlines()[0]}</b>\n\n"
                    f"Supported: {hint}",
                )
        return

    result = parse_trade_message(body)
    if isinstance(result, Failure):
        await message.reply(f"❌ Format error:\n\n{result.error}")
        return

    user = message.from_user
    try:
        trade = await container.trades.create_from_parsed(
            user_id=user.id,
            user_name=user.full_name,
            username=user.username,
            parsed=result.value,
            setup_chat_id=message.chat.id,
            setup_message_id=message.message_id,
            setup_thread_id=message.message_thread_id,
            recorded_at=message.date,
        )
    except ValueError as e:
        await message.reply(f"❌ {e}")
        return
    except Exception as exc:
        log.exception("Failed to create trade for user %s", user.id)
        await message.reply(f"❌ Failed to record trade: {exc}")
        return

    trade = await container.trades.check_price_triggers(trade, full_replay=True)
    await container.notify.confirm_setup(message.bot, trade, message.message_id)
    if trade.status == TradeStatus.CLOSED:
        await container.notify.notify_trade_closed(message.bot, trade)
