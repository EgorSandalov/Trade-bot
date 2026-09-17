from aiogram import Bot
from aiogram.enums import ChatMemberStatus

from bot.config import ADMIN_IDS
from bot.groups import CONFIGURED_GROUPS, get_group, primary_chat_id


class AccessService:
    def is_private_chat(self, chat_id: int) -> bool:
        return chat_id > 0

    def is_admin(self, user_id: int) -> bool:
        return user_id in ADMIN_IDS

    async def is_allowed_chat(self, bot: Bot, chat_id: int, user_id: int) -> bool:
        if self.is_private_chat(chat_id):
            if self.is_admin(user_id):
                return True
            if CONFIGURED_GROUPS:
                return await self.is_group_member(bot, user_id)
            return True
        if get_group(chat_id) is not None:
            return True
        if CONFIGURED_GROUPS:
            return self.is_admin(user_id)
        return True

    async def resolve_trade_chat_id(
        self, bot: Bot, user_id: int, chat_id: int
    ) -> int | None:
        """Group chat id for trade DB routing (DM → first configured group user belongs to)."""
        if chat_id < 0:
            return chat_id
        for group in CONFIGURED_GROUPS.values():
            if await self._is_member_of(bot, user_id, group.chat_id):
                return group.chat_id
        return primary_chat_id()

    @staticmethod
    def is_public_setup_command(text: str | None) -> bool:
        """IDs for .env — allowed in any group, even before it is in GROUPS."""
        if not text:
            return False
        cmd = text.split()[0].split("@")[0].lower()
        return cmd in ("/chat_id", "/myid")

    async def is_group_member(
        self,
        bot: Bot,
        user_id: int,
        chat_id: int | None = None,
    ) -> bool:
        if chat_id is not None and get_group(chat_id) is not None:
            return await self._is_member_of(bot, user_id, chat_id)
        if not CONFIGURED_GROUPS:
            return True
        for group in CONFIGURED_GROUPS.values():
            if await self._is_member_of(bot, user_id, group.chat_id):
                return True
        return False

    async def _is_member_of(self, bot: Bot, user_id: int, chat_id: int) -> bool:
        try:
            member = await bot.get_chat_member(chat_id, user_id)
            return member.status in (
                ChatMemberStatus.MEMBER,
                ChatMemberStatus.ADMINISTRATOR,
                ChatMemberStatus.CREATOR,
                ChatMemberStatus.RESTRICTED,
            )
        except Exception:
            return False

    def is_setups_topic(self, chat_id: int, thread_id: int | None) -> bool:
        group = get_group(chat_id)
        if group is None:
            return False
        if group.setups_topic_id is None:
            return True
        return thread_id == group.setups_topic_id

    def is_general_topic(self, chat_id: int, thread_id: int | None) -> bool:
        """Any group topic except Setups counts as General."""
        group = get_group(chat_id)
        if group is None:
            return False
        if group.setups_topic_id is not None and thread_id == group.setups_topic_id:
            return False
        return True

    async def can_create_setup(self, bot: Bot, user_id: int, chat_id: int, thread_id: int | None) -> bool:
        if not await self.is_group_member(bot, user_id, chat_id):
            return False
        return self.is_setups_topic(chat_id, thread_id)

    async def can_use_general(self, bot: Bot, user_id: int, chat_id: int, thread_id: int | None) -> bool:
        if self.is_private_chat(chat_id):
            return await self.is_group_member(bot, user_id)
        if not await self.is_group_member(bot, user_id, chat_id):
            return False
        return self.is_general_topic(chat_id, thread_id)
