from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.services.access_service import AccessService


class AccessMiddleware(BaseMiddleware):
    """Private chat — group members. Groups — configured GROUPS only."""

    def __init__(self) -> None:
        self.access = AccessService()

    async def __call__(self, handler, event: TelegramObject, data: dict):
        user_id: int | None = None
        chat_id: int | None = None
        bot = None

        if isinstance(event, Message):
            if not event.from_user:
                return
            user_id = event.from_user.id
            chat_id = event.chat.id
            bot = event.bot
            if chat_id < 0 and self.access.is_public_setup_command(event.text):
                return await handler(event, data)
        elif isinstance(event, CallbackQuery):
            if not event.from_user or not event.message:
                return
            user_id = event.from_user.id
            chat_id = event.message.chat.id
            bot = event.bot
        else:
            return await handler(event, data)

        if bot is None or not await self.access.is_allowed_chat(bot, chat_id, user_id):
            return

        return await handler(event, data)
