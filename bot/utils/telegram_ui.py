"""Helpers for Telegram message edit and callback de-duplication."""



from __future__ import annotations



import json

import logging

import re



from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message



log = logging.getLogger(__name__)



CAPTION_MAX_LEN = 1024

_MESSAGE_MAX_LEN = 4096



_SETUP_MARKERS = ("type:", "leverage:", "sl:", "tp", "entry:", "comment:")





def message_text(msg: Message | None) -> str:

    if not msg:

        return ""

    return (msg.text or msg.caption or "").strip()





def _markup_key(markup: InlineKeyboardMarkup | None) -> str:

    if markup is None:

        return ""

    try:

        return json.dumps(markup.model_dump(), sort_keys=True)

    except Exception:

        return repr(markup)





def _is_media_message(message: Message) -> bool:

    return bool(message.photo or message.animation or message.video)





def _reply_kwargs(message: Message) -> dict:

    kwargs: dict = {"parse_mode": "HTML"}

    if message.message_thread_id is not None:

        kwargs["message_thread_id"] = message.message_thread_id

    return kwargs





async def delete_message(message: Message | None) -> None:

    if not message:

        return

    try:

        await message.delete()

    except Exception:

        pass





def looks_like_setup_edit(text: str) -> bool:

    """True if the message resembles an edited trade setup (not a command or chit-chat)."""

    body = text.strip()

    if not body or body.startswith("/"):

        return False

    if "\n" not in body:

        return False

    lower = body.lower()

    return any(marker in lower for marker in _SETUP_MARKERS)





def telegram_html_issues(text: str) -> list[str]:

    """Find common HTML mistakes that make Telegram reject edit/send."""

    issues: list[str] = []

    if re.search(r"<\s*pre\s*>", text, re.IGNORECASE):

        opens = len(re.findall(r"<\s*pre\s*>", text, re.IGNORECASE))

        closes = len(re.findall(r"<\s*/\s*pre\s*>", text, re.IGNORECASE))

        if opens != closes:

            issues.append(f"unbalanced <pre> tags ({opens} open, {closes} close)")

    return issues





async def _send_fallback(
    message: Message,
    text: str,
    reply_markup: InlineKeyboardMarkup | None,
) -> Message:

    return await message.answer(text, reply_markup=reply_markup, **_reply_kwargs(message))





async def edit_menu_message(

    message: Message,

    text: str,

    reply_markup: InlineKeyboardMarkup | None = None,

) -> Message:

    """Edit text or media caption; fall back to a new in-thread message."""

    issues = telegram_html_issues(text)

    if issues:

        log.error("Invalid Telegram HTML before edit: %s", "; ".join(issues))



    limit = CAPTION_MAX_LEN if _is_media_message(message) else _MESSAGE_MAX_LEN

    if len(text) > limit and _is_media_message(message):

        log.info("Edit text %d chars exceeds caption limit — sending as text message", len(text))

        return await _send_fallback(message, text, reply_markup)



    try:

        if _is_media_message(message):

            await message.edit_caption(

                caption=text,

                reply_markup=reply_markup,

                parse_mode="HTML",

            )

        else:

            await message.edit_text(

                text,

                reply_markup=reply_markup,

                parse_mode="HTML",

            )

        return message

    except Exception as exc:

        log.warning("edit_menu_message failed (%s), sending fallback", exc)



    try:

        return await _send_fallback(message, text, reply_markup)

    except Exception:

        log.exception("edit_menu_message fallback also failed")

        return message





async def edit_bot_message(

    bot,

    chat_id: int,

    message_id: int,

    text: str,

    reply_markup: InlineKeyboardMarkup | None = None,

    *,

    message_thread_id: int | None = None,

    anchor_message: Message | None = None,

) -> Message | None:

    """Edit by chat/message id — works for both text and photo captions."""

    thread_kw = {"message_thread_id": message_thread_id} if message_thread_id is not None else {}

    try:

        await bot.edit_message_text(

            text,

            chat_id,

            message_id,

            reply_markup=reply_markup,

            parse_mode="HTML",

            **thread_kw,

        )

        return None

    except Exception:

        pass

    try:

        await bot.edit_message_caption(

            caption=text,

            chat_id=chat_id,

            message_id=message_id,

            reply_markup=reply_markup,

            parse_mode="HTML",

            **thread_kw,

        )

        return None

    except Exception as exc:

        log.warning("edit_bot_message failed for %s/%s: %s", chat_id, message_id, exc)



    if anchor_message is not None:

        try:

            return await _send_fallback(anchor_message, text, reply_markup)

        except Exception:

            log.exception("edit_bot_message fallback failed for %s/%s", chat_id, message_id)

    return None





async def answer_if_unchanged(

    callback: CallbackQuery,

    text: str,

    reply_markup: InlineKeyboardMarkup | None = None,

) -> bool:

    """Return True if content is already shown — caller should stop."""

    if not callback.message:

        return False

    if message_text(callback.message) != text.strip():

        return False

    current = callback.message.reply_markup

    if _markup_key(current) != _markup_key(reply_markup):

        return False

    await callback.answer()

    return True

