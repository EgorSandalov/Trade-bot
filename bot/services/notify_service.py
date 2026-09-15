from collections.abc import Awaitable, Callable

from aiogram import Bot

from bot.config import EPIC_LOSS_TRADE_PERSONAL_PCT, EPIC_TRADE_PERSONAL_PCT
from bot.domain.enums import TradeStatus
from bot.domain.models import Trade
from bot.groups import primary_chat_id, setups_topic_for_chat
from bot.services.profile_service import ProfileService
from bot.utils.formatters import format_close_result, format_setup_confirmed


def _setup_chat_id(trade: Trade) -> int | None:
    return trade.setup_chat_id or primary_chat_id()


def _setup_thread_id(trade: Trade) -> int | None:
    return trade.setup_thread_id or setups_topic_for_chat(_setup_chat_id(trade))


class NotifyService:
    def __init__(self, profiles: ProfileService, trade_repo=None) -> None:
        if profiles is None:
            raise ValueError("Profile service must be provided")
        self._profiles = profiles
        self._trade_repo = trade_repo

    async def confirm_setup(self, bot: Bot, trade: Trade, reply_to_message_id: int) -> None:
        chat_id = _setup_chat_id(trade)
        if not chat_id:
            return
        await bot.send_message(
            chat_id=chat_id,
            text=format_setup_confirmed(trade),
            reply_to_message_id=reply_to_message_id,
            message_thread_id=_setup_thread_id(trade),
        )

    async def notify_trade_closed(self, bot: Bot, trade: Trade) -> None:
        if trade.status != TradeStatus.CLOSED:
            return
        chat_id = _setup_chat_id(trade)
        if not chat_id or not trade.setup_message_id:
            return
        thread_id = _setup_thread_id(trade)
        events = None
        if self._trade_repo and trade.id:
            events = await self._trade_repo.get_events(trade.id)
        await bot.send_message(
            chat_id=chat_id,
            text=format_close_result(trade, events),
            reply_to_message_id=trade.setup_message_id,
            message_thread_id=thread_id,
        )
        personal = trade.result_personal_move_pct or 0.0
        if personal >= EPIC_TRADE_PERSONAL_PCT:
            await self._send_epic_reaction(
                bot,
                trade,
                media_getter=self._profiles.get_reaction_media,
                emoji="🔥",
                threshold=EPIC_TRADE_PERSONAL_PCT,
                direction="≥",
            )
        elif personal <= EPIC_LOSS_TRADE_PERSONAL_PCT:
            await self._send_epic_reaction(
                bot,
                trade,
                media_getter=self._profiles.get_loss_reaction_media,
                emoji="💀",
                threshold=EPIC_LOSS_TRADE_PERSONAL_PCT,
                direction="≤",
            )

    async def _send_epic_reaction(
        self,
        bot: Bot,
        trade: Trade,
        *,
        media_getter: Callable[[int], Awaitable[tuple[str, str] | None]],
        emoji: str,
        threshold: float,
        direction: str,
    ) -> None:
        chat_id = _setup_chat_id(trade)
        if not chat_id:
            return
        thread_id = _setup_thread_id(trade)
        media = await media_getter(trade.user_id)
        if media:
            file_id, kind = media
            if kind == "animation":
                await bot.send_animation(
                    chat_id=chat_id,
                    animation=file_id,
                    reply_to_message_id=trade.setup_message_id,
                    message_thread_id=thread_id,
                )
            else:
                await bot.send_sticker(
                    chat_id=chat_id,
                    sticker=file_id,
                    reply_to_message_id=trade.setup_message_id,
                    message_thread_id=thread_id,
                )
            return
        await bot.send_message(
            chat_id=chat_id,
            text=(
                f"{emoji} Personal {direction} {threshold:.0f}% — "
                f"<a href=\"tg://user?id={trade.user_id}\">{trade.user_name}</a>, "
                "set your epic sticker via /myprofile"
            ),
            reply_to_message_id=trade.setup_message_id,
            message_thread_id=thread_id,
        )
