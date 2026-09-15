from aiogram.filters import Filter
from aiogram.types import Message

from bot.services.access_service import AccessService


class InGeneralOrPrivateFilter(Filter):
    """Match only General topic (or private chat for admin)."""

    async def __call__(self, message: Message) -> bool:
        access = AccessService()
        if access.is_private_chat(message.chat.id):
            return True
        return access.is_general_topic(message.chat.id, message.message_thread_id)
