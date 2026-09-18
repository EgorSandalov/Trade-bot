from dataclasses import dataclass
from pathlib import Path

from aiogram import Bot
from aiogram.types import (
    FSInputFile,
    InputMediaAnimation,
    InputMediaPhoto,
    InlineKeyboardMarkup,
    Message,
)

from bot.abstractions.repositories import IProfileRepository
from bot.config import GROUP_BANNER_PATH, PROFILE_PHOTOS_DIR
from bot.utils.banner import ensure_group_banner

_SUPPORTED_TYPES = frozenset({"photo", "animation"})


@dataclass
class ProfileMedia:
    kind: str  # photo | animation
    path: Path | None = None
    file_id: str | None = None


class ProfileService:
    def __init__(self, repo: IProfileRepository) -> None:
        if repo is None:
            raise ValueError("Profile repository must be provided")
        self._repo = repo
        PROFILE_PHOTOS_DIR.mkdir(parents=True, exist_ok=True)
        ensure_group_banner(GROUP_BANNER_PATH)

    def group_banner(self) -> Path:
        return ensure_group_banner(GROUP_BANNER_PATH)

    def user_photo_path(self, user_id: int) -> Path:
        return PROFILE_PHOTOS_DIR / f"{user_id}.jpg"

    def user_animation_path(self, user_id: int) -> Path:
        return PROFILE_PHOTOS_DIR / f"{user_id}_anim.mp4"

    async def get_profile_media(self, user_id: int | None) -> ProfileMedia:
        if user_id is None:
            return ProfileMedia("photo", path=self.group_banner())

        profile = await self._repo.get_profile(user_id)
        if not profile or profile.profile_type not in _SUPPORTED_TYPES:
            return ProfileMedia("photo", path=self.group_banner())

        if profile.profile_type == "animation" and profile.telegram_file_id:
            path = (
                Path(profile.photo_path)
                if profile.photo_path and Path(profile.photo_path).exists()
                else None
            )
            return ProfileMedia("animation", path=path, file_id=profile.telegram_file_id)

        if profile.photo_path and Path(profile.photo_path).exists():
            return ProfileMedia("photo", path=Path(profile.photo_path))

        return ProfileMedia("photo", path=self.group_banner())

    async def get_profile_photo(self, user_id: int) -> Path:
        media = await self.get_profile_media(user_id)
        if media.path:
            return media.path
        return self.group_banner()

    async def has_custom_profile(self, user_id: int) -> bool:
        profile = await self._repo.get_profile(user_id)
        if not profile or profile.profile_type not in _SUPPORTED_TYPES:
            return False
        if profile.profile_type == "animation":
            return bool(profile.telegram_file_id)
        return bool(profile.photo_path and Path(profile.photo_path).exists())

    async def save_profile_photo(
        self, bot: Bot, user_id: int, file_id: str,
        *, display_name: str | None = None, username: str | None = None,
    ) -> Path:
        dest = self.user_photo_path(user_id)
        await self._download_file(bot, file_id, dest)
        await self._repo.save_banner(
            user_id, "photo", str(dest), file_id,
            display_name=display_name, username=username,
        )
        return dest

    async def save_profile_animation(
        self, bot: Bot, user_id: int, file_id: str,
        *, display_name: str | None = None, username: str | None = None,
    ) -> str:
        dest = self.user_animation_path(user_id)
        try:
            await self._download_file(bot, file_id, dest)
            path = str(dest)
        except ValueError:
            path = ""
        await self._repo.save_banner(
            user_id, "animation", path or None, file_id,
            display_name=display_name, username=username,
        )
        return file_id

    async def get_reaction_sticker(self, user_id: int) -> str | None:
        profile = await self._repo.get_profile(user_id)
        if not profile:
            return None
        return profile.reaction_sticker_file_id

    async def get_reaction_media(self, user_id: int) -> tuple[str, str] | None:
        profile = await self._repo.get_profile(user_id)
        if not profile or not profile.reaction_sticker_file_id:
            return None
        return profile.reaction_sticker_file_id, profile.reaction_kind or "sticker"

    async def has_reaction_sticker(self, user_id: int) -> bool:
        return bool(await self.get_reaction_sticker(user_id))

    async def save_reaction_sticker(
        self,
        user_id: int,
        file_id: str,
        *,
        kind: str = "sticker",
        display_name: str | None = None,
        username: str | None = None,
    ) -> None:
        await self._repo.save_reaction_sticker(
            user_id, file_id, kind=kind,
            display_name=display_name, username=username,
        )

    async def get_loss_reaction_sticker(self, user_id: int) -> str | None:
        profile = await self._repo.get_profile(user_id)
        if not profile:
            return None
        return profile.loss_reaction_sticker_file_id

    async def get_loss_reaction_media(self, user_id: int) -> tuple[str, str] | None:
        profile = await self._repo.get_profile(user_id)
        if not profile or not profile.loss_reaction_sticker_file_id:
            return None
        return profile.loss_reaction_sticker_file_id, profile.loss_reaction_kind or "sticker"

    async def has_loss_reaction_sticker(self, user_id: int) -> bool:
        return bool(await self.get_loss_reaction_sticker(user_id))

    async def save_loss_reaction_sticker(
        self,
        user_id: int,
        file_id: str,
        *,
        kind: str = "sticker",
        display_name: str | None = None,
        username: str | None = None,
    ) -> None:
        await self._repo.save_loss_reaction_sticker(
            user_id, file_id, kind=kind,
            display_name=display_name, username=username,
        )

    async def send_card(
        self,
        message: Message,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        user_id: int | None = None,
        *,
        photo_path: Path | None = None,
    ) -> Message:
        media = await self._resolve_card_media(user_id, photo_path)
        if media.kind == "animation":
            return await message.answer_animation(
                self._animation_input(media),
                caption=caption,
                reply_markup=reply_markup,
                parse_mode="HTML",
            )
        path = media.path or self.group_banner()
        return await message.answer_photo(
            FSInputFile(path),
            caption=caption,
            reply_markup=reply_markup,
            parse_mode="HTML",
        )

    async def update_card(
        self,
        message: Message,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None = None,
        user_id: int | None = None,
        *,
        photo_path: Path | None = None,
    ) -> None:
        media = await self._resolve_card_media(user_id, photo_path)
        if media.kind == "animation":
            anim = self._animation_input(media)
            if message.animation or message.photo:
                await message.edit_media(
                    InputMediaAnimation(media=anim, caption=caption, parse_mode="HTML"),
                    reply_markup=reply_markup,
                )
                return
            await self._replace_message_with_animation(message, anim, caption, reply_markup)
            return

        path = media.path or self.group_banner()
        photo = FSInputFile(path)
        if message.photo or message.animation:
            await message.edit_media(
                InputMediaPhoto(media=photo, caption=caption, parse_mode="HTML"),
                reply_markup=reply_markup,
            )
            return
        await self._replace_message_with_photo(message, photo, caption, reply_markup)

    async def _resolve_card_media(
        self,
        user_id: int | None,
        photo_path: Path | None,
    ) -> ProfileMedia:
        if photo_path:
            return ProfileMedia("photo", path=photo_path)
        if user_id is not None:
            return await self.get_profile_media(user_id)
        return ProfileMedia("photo", path=self.group_banner())

    @staticmethod
    def _animation_input(media: ProfileMedia) -> str | FSInputFile:
        if media.file_id:
            return media.file_id
        if media.path:
            return FSInputFile(media.path)
        return FSInputFile(GROUP_BANNER_PATH)

    @staticmethod
    async def _replace_message_with_animation(
        message: Message,
        animation,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None,
    ) -> None:
        chat_id = message.chat.id
        thread_id = message.message_thread_id
        await message.delete()
        await message.bot.send_animation(
            chat_id=chat_id,
            animation=animation,
            caption=caption,
            reply_markup=reply_markup,
            message_thread_id=thread_id,
            parse_mode="HTML",
        )

    @staticmethod
    async def _replace_message_with_photo(
        message: Message,
        photo: FSInputFile,
        caption: str,
        reply_markup: InlineKeyboardMarkup | None,
    ) -> None:
        chat_id = message.chat.id
        thread_id = message.message_thread_id
        await message.delete()
        await message.bot.send_photo(
            chat_id=chat_id,
            photo=photo,
            caption=caption,
            reply_markup=reply_markup,
            message_thread_id=thread_id,
            parse_mode="HTML",
        )

    async def _download_file(self, bot: Bot, file_id: str, dest: Path) -> None:
        file = await bot.get_file(file_id)
        if not file.file_path:
            raise ValueError("Cannot download file from Telegram")
        await bot.download_file(file.file_path, destination=dest)
