from aiogram.types import Message

from bot.services.access_service import AccessService


async def require_general(message: Message, access: AccessService) -> bool:
    """Commands and FSM replies only in General (or private admin chat)."""
    if not message.from_user:
        return False
    ok = await access.can_use_general(
        message.bot, message.from_user.id, message.chat.id, message.message_thread_id
    )
    if not ok:
        await message.reply("Use commands in General (not Setups).")
        return False
    return True
