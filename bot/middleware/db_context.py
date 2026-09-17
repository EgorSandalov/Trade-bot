from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database.context import set_request_chat_id
from bot.services.access_service import AccessService


class DbContextMiddleware(BaseMiddleware):
    """Route DB access to the group where the update was received."""

    def __init__(self) -> None:
        self.access = AccessService()

    async def __call__(self, handler, event: TelegramObject, data: dict):
        chat_id: int | None = None
        user_id: int | None = None
        bot = None
        if isinstance(event, Message):
            chat_id = event.chat.id
            user_id = event.from_user.id if event.from_user else None
            bot = event.bot
        elif isinstance(event, CallbackQuery) and event.message:
            chat_id = event.message.chat.id
            user_id = event.from_user.id if event.from_user else None
            bot = event.bot
        if chat_id is not None and chat_id > 0 and bot is not None and user_id is not None:
            chat_id = await self.access.resolve_trade_chat_id(bot, user_id, chat_id)
        set_request_chat_id(chat_id)
        try:
            return await handler(event, data)
        finally:
            set_request_chat_id(None)
