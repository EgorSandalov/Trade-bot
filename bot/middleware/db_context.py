from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

from bot.database.context import set_request_chat_id


class DbContextMiddleware(BaseMiddleware):
    """Route DB access to the group where the update was received."""

    async def __call__(self, handler, event: TelegramObject, data: dict):
        chat_id: int | None = None
        if isinstance(event, Message):
            chat_id = event.chat.id
        elif isinstance(event, CallbackQuery) and event.message:
            chat_id = event.message.chat.id
        set_request_chat_id(chat_id)
        try:
            return await handler(event, data)
        finally:
            set_request_chat_id(None)
