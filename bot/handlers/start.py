from aiogram import F, Router
from aiogram.filters import Command, CommandStart
from aiogram.types import CallbackQuery, Message

from bot.config import COMMUNITY_NAME
from bot.groups import CONFIGURED_GROUPS, get_group
from bot.services.access_service import AccessService
from bot.utils.faq import (
    faq_language_kb,
    faq_page_count,
    faq_page_kb,
    faq_picker_text,
    format_faq_page,
)
from bot.utils.formatters import format_help
from bot.utils.telegram_ui import answer_if_unchanged

router = Router()
access = AccessService()

# All FAQ messages in a chat (any user, any language) — delete together
_chat_faq_ids: dict[int, list[int]] = {}


async def _clear_chat_faq(bot, chat_id: int, *, keep_id: int | None = None) -> None:
    kept: list[int] = []
    for mid in _chat_faq_ids.get(chat_id, []):
        if mid == keep_id:
            kept.append(mid)
            continue
        try:
            await bot.delete_message(chat_id, mid)
        except Exception:
            pass
    _chat_faq_ids[chat_id] = kept


def _track_faq(chat_id: int, message_id: int) -> None:
    _chat_faq_ids[chat_id] = [message_id]


async def _edit_or_send(
    bot,
    chat_id: int,
    text: str,
    reply_markup,
    *,
    edit_message: Message | None = None,
) -> int:
    if edit_message:
        try:
            await edit_message.edit_text(text, reply_markup=reply_markup)
            return edit_message.message_id
        except Exception:
            pass
    await _clear_chat_faq(bot, chat_id)
    sent = await bot.send_message(chat_id, text, reply_markup=reply_markup)
    return sent.message_id


@router.message(CommandStart())
@router.message(Command("help"))
async def cmd_help(message: Message) -> None:
    if not message.from_user:
        return
    if CONFIGURED_GROUPS and not await access.is_group_member(message.bot, message.from_user.id):
        await message.answer(f"🔒 {COMMUNITY_NAME}\n\nБот только для участников группы.")
        return
    await message.answer(format_help())


@router.message(Command("faq"))
async def cmd_faq(message: Message) -> None:
    if not message.from_user:
        return
    if CONFIGURED_GROUPS and not await access.is_group_member(message.bot, message.from_user.id):
        await message.answer(f"🔒 {COMMUNITY_NAME}\n\nБот только для участников группы.")
        return

    chat_id = message.chat.id
    await _clear_chat_faq(message.bot, chat_id)
    sent = await message.answer(faq_picker_text(), reply_markup=faq_language_kb())
    _track_faq(chat_id, sent.message_id)


@router.callback_query(F.data.startswith("faq:"))
async def faq_callback(callback: CallbackQuery) -> None:
    if not callback.from_user or not callback.message:
        return
    if CONFIGURED_GROUPS and not await access.is_group_member(callback.bot, callback.from_user.id):
        await callback.answer("Members only", show_alert=True)
        return

    parts = callback.data.split(":")
    action = parts[1] if len(parts) > 1 else "menu"
    chat_id = callback.message.chat.id
    msg = callback.message

    if action == "noop":
        await callback.answer()
        return

    if action == "menu":
        if await answer_if_unchanged(callback, faq_picker_text(), faq_language_kb()):
            return
        await callback.answer()
        await _clear_chat_faq(callback.bot, chat_id, keep_id=msg.message_id)
        mid = await _edit_or_send(
            callback.bot,
            chat_id,
            faq_picker_text(),
            faq_language_kb(),
            edit_message=msg,
        )
        _track_faq(chat_id, mid)
        return

    if action not in ("ru", "en"):
        await callback.answer()
        return

    page = int(parts[2]) if len(parts) > 2 else 0
    total = faq_page_count(action)
    page = max(0, min(page, total - 1))
    text = format_faq_page(action, page)
    kb = faq_page_kb(action, page, total)
    if await answer_if_unchanged(callback, text, kb):
        return

    await callback.answer()
    await _clear_chat_faq(callback.bot, chat_id, keep_id=msg.message_id)
    mid = await _edit_or_send(
        callback.bot,
        chat_id,
        format_faq_page(action, page),
        faq_page_kb(action, page, total),
        edit_message=msg,
    )
    _track_faq(chat_id, mid)


@router.message(Command("chat_id"))
async def cmd_chat_id(message: Message) -> None:
    if not message.chat:
        return
    thread = message.message_thread_id
    group = get_group(message.chat.id)
    setups = "?"
    general = "?"
    topic_hint = "Send /chat_id from Setups and General topics"
    if group:
        setups = str(group.setups_topic_id or "?")
        general = str(group.general_topic_id or "1")
        if thread is not None and group.setups_topic_id and thread == group.setups_topic_id:
            setups = str(thread)
            topic_hint = "← Setups topic (general from config)"
        elif thread is not None:
            general = str(thread)
            topic_hint = "← General topic (setups from config)"
    elif thread is not None:
        setups = str(thread)
        general = "1"
        topic_hint = "← Setups? Send also from General"

    lines = [
        "<b>IDs for .env</b>",
        "",
        f"<code>GROUPS={message.chat.id}:{setups}:{general}:your.db</code>",
        topic_hint,
        "",
        "Multiple groups: separate with <code>;</code>",
        "Example:",
        "<code>GROUPS=-100111:3:1:alpha.db;-100222:24101:1:prod.db</code>",
    ]
    if message.from_user:
        lines.extend(["", f"Your ID: <code>{message.from_user.id}</code>"])
    await message.answer("\n".join(lines))


@router.message(Command("myid"))
async def cmd_myid(message: Message) -> None:
    if not message.from_user:
        return
    await message.answer(f"Your Telegram ID:\n<code>{message.from_user.id}</code>")
