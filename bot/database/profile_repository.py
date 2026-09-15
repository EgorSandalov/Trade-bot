from dataclasses import dataclass
from datetime import datetime, timezone

from bot.database.db import get_profiles_connection


@dataclass
class UserProfile:
    user_id: int
    profile_type: str  # photo | animation
    photo_path: str | None
    telegram_file_id: str | None
    custom_emoji_id: str | None
    emoji_fallback: str | None
    reaction_sticker_file_id: str | None
    display_name: str | None
    username: str | None
    updated_at: datetime
    reaction_kind: str = "sticker"
    loss_reaction_sticker_file_id: str | None = None
    loss_reaction_kind: str = "sticker"


class ProfileRepository:
    async def get_profile(self, user_id: int) -> UserProfile | None:
        async with get_profiles_connection() as db:
            row = await (
                await db.execute(
                    """
                    SELECT user_id, profile_type, photo_path, telegram_file_id,
                           custom_emoji_id, emoji_fallback, reaction_sticker_file_id,
                           reaction_kind, loss_reaction_sticker_file_id, loss_reaction_kind,
                           display_name, username, updated_at
                    FROM user_profiles WHERE user_id = ?
                    """,
                    (user_id,),
                )
            ).fetchone()
            if not row:
                return None
            keys = row.keys()
            return UserProfile(
                user_id=row["user_id"],
                profile_type=row["profile_type"] if "profile_type" in keys else "photo",
                photo_path=row["photo_path"],
                telegram_file_id=row["telegram_file_id"] if "telegram_file_id" in keys else None,
                custom_emoji_id=row["custom_emoji_id"] if "custom_emoji_id" in keys else None,
                emoji_fallback=row["emoji_fallback"] if "emoji_fallback" in keys else None,
                reaction_sticker_file_id=(
                    row["reaction_sticker_file_id"]
                    if "reaction_sticker_file_id" in keys
                    else None
                ),
                reaction_kind=row["reaction_kind"] if "reaction_kind" in keys and row["reaction_kind"] else "sticker",
                loss_reaction_sticker_file_id=(
                    row["loss_reaction_sticker_file_id"]
                    if "loss_reaction_sticker_file_id" in keys
                    else None
                ),
                loss_reaction_kind=(
                    row["loss_reaction_kind"]
                    if "loss_reaction_kind" in keys and row["loss_reaction_kind"]
                    else "sticker"
                ),
                display_name=row["display_name"] if "display_name" in keys else None,
                username=row["username"] if "username" in keys else None,
                updated_at=datetime.fromisoformat(row["updated_at"]),
            )

    async def _touch_user_info(
        self,
        db,
        user_id: int,
        display_name: str | None,
        username: str | None,
    ) -> None:
        if display_name or username is not None:
            await db.execute(
                """
                UPDATE user_profiles SET
                    display_name = COALESCE(?, display_name),
                    username = COALESCE(?, username)
                WHERE user_id = ?
                """,
                (display_name, username, user_id),
            )

    async def save_banner(
        self,
        user_id: int,
        profile_type: str,
        photo_path: str | None,
        telegram_file_id: str | None,
        *,
        display_name: str | None = None,
        username: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with get_profiles_connection() as db:
            await db.execute(
                """
                INSERT INTO user_profiles (
                    user_id, profile_type, photo_path, telegram_file_id,
                    display_name, username, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    profile_type = excluded.profile_type,
                    photo_path = excluded.photo_path,
                    telegram_file_id = excluded.telegram_file_id,
                    display_name = COALESCE(excluded.display_name, display_name),
                    username = COALESCE(excluded.username, username),
                    updated_at = excluded.updated_at
                """,
                (user_id, profile_type, photo_path, telegram_file_id, display_name, username, now),
            )
            await db.commit()

    async def save_reaction_sticker(
        self,
        user_id: int,
        file_id: str,
        *,
        kind: str = "sticker",
        display_name: str | None = None,
        username: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with get_profiles_connection() as db:
            existing = await (
                await db.execute(
                    "SELECT user_id FROM user_profiles WHERE user_id = ?",
                    (user_id,),
                )
            ).fetchone()
            if existing:
                await db.execute(
                    """
                    UPDATE user_profiles SET
                        reaction_sticker_file_id = ?,
                        reaction_kind = ?,
                        display_name = COALESCE(?, display_name),
                        username = COALESCE(?, username),
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (file_id, kind, display_name, username, now, user_id),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO user_profiles (
                        user_id, profile_type, reaction_sticker_file_id, reaction_kind,
                        display_name, username, updated_at
                    ) VALUES (?, 'photo', ?, ?, ?, ?, ?)
                    """,
                    (user_id, file_id, kind, display_name, username, now),
                )
            await db.commit()

    async def save_loss_reaction_sticker(
        self,
        user_id: int,
        file_id: str,
        *,
        kind: str = "sticker",
        display_name: str | None = None,
        username: str | None = None,
    ) -> None:
        now = datetime.now(timezone.utc).isoformat()
        async with get_profiles_connection() as db:
            existing = await (
                await db.execute(
                    "SELECT user_id FROM user_profiles WHERE user_id = ?",
                    (user_id,),
                )
            ).fetchone()
            if existing:
                await db.execute(
                    """
                    UPDATE user_profiles SET
                        loss_reaction_sticker_file_id = ?,
                        loss_reaction_kind = ?,
                        display_name = COALESCE(?, display_name),
                        username = COALESCE(?, username),
                        updated_at = ?
                    WHERE user_id = ?
                    """,
                    (file_id, kind, display_name, username, now, user_id),
                )
            else:
                await db.execute(
                    """
                    INSERT INTO user_profiles (
                        user_id, profile_type, loss_reaction_sticker_file_id, loss_reaction_kind,
                        display_name, username, updated_at
                    ) VALUES (?, 'photo', ?, ?, ?, ?, ?)
                    """,
                    (user_id, file_id, kind, display_name, username, now),
                )
            await db.commit()
