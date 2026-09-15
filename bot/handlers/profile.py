import logging

from aiogram import F, Router
from aiogram.filters import Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, Message

from bot.app.container import AppContainer
from bot.handlers.common import require_general
from bot.handlers.states import ProfileStates
from bot.handlers.trade_flow import end_trade_flow
from bot.keyboards.menus import profile_menu_kb, profile_preview_back_kb, profile_saved_back_kb
from bot.services.profile_service import ProfileService
from bot.utils.telegram_ui import answer_if_unchanged, delete_message, edit_menu_message

router = Router()
log = logging.getLogger(__name__)


def _owner_line(*, display_name: str, username: str | None) -> str:
    if username:
        return f"👤 <b>Your profile</b> — {display_name} (@{username})"
    return f"👤 <b>Your profile</b> — {display_name}"


def _profile_menu_text(
    *,
    display_name: str,
    username: str | None,
    has_banner: bool,
    has_sticker: bool,
    has_loss_sticker: bool,
) -> str:
    banner_status = "set" if has_banner else "not set"
    sticker_status = "set" if has_sticker else "not set"
    loss_sticker_status = "set" if has_loss_sticker else "not set"
    return (
        f"{_owner_line(display_name=display_name, username=username)}\n\n"
        "Banner and stickers below are <b>yours</b>.\n"
        "In a group chat, buttons always change <b>your</b> profile,\n"
        "even on someone else's message.\n\n"
        f"🖼 Banner: {banner_status}\n"
        f"🔥 Epic sticker (+100%): {sticker_status}\n"
        f"💀 Epic sticker (-100%): {loss_sticker_status}\n\n"
        "Tap a button below"
    )


def _banner_prompt(*, display_name: str, username: str | None) -> str:
    return (
        f"{_owner_line(display_name=display_name, username=username)}\n\n"
        "<b>🖼 Banner</b>\n\n"
        "Send a photo or GIF.\n"
        "Shown in leaderboard.\n\n"
        "Tap ◀ Back to return."
    )


def _reaction_prompt(*, display_name: str, username: str | None) -> str:
    return (
        f"{_owner_line(display_name=display_name, username=username)}\n\n"
        "<b>🔥 Epic sticker (+100%)</b>\n\n"
        "Sent when personal move ≥ +100%.\n"
        "Send a sticker from any pack\n"
        "or a GIF / animation.\n\n"
        "Tap ◀ Back to return."
    )


def _loss_reaction_prompt(*, display_name: str, username: str | None) -> str:
    return (
        f"{_owner_line(display_name=display_name, username=username)}\n\n"
        "<b>💀 Epic sticker (-100%)</b>\n\n"
        "Sent when personal move ≤ -100%.\n"
        "Send a sticker from any pack\n"
        "or a GIF / animation.\n\n"
        "Tap ◀ Back to return."
    )


def _user_from_message(message: Message) -> tuple[str, str | None]:
    assert message.from_user
    return message.from_user.full_name, message.from_user.username


def _user_from_callback(callback: CallbackQuery) -> tuple[str, str | None]:
    assert callback.from_user
    return callback.from_user.full_name, callback.from_user.username


async def _profile_flags(profiles: ProfileService, user_id: int) -> tuple[bool, bool, bool]:
    has_banner = await profiles.has_custom_profile(user_id)
    has_sticker = await profiles.has_reaction_sticker(user_id)
    has_loss_sticker = await profiles.has_loss_reaction_sticker(user_id)
    return has_banner, has_sticker, has_loss_sticker


async def _profile_kb(profiles: ProfileService, user_id: int, *, hide: str | None = None):
    has_banner, has_sticker, has_loss_sticker = await _profile_flags(profiles, user_id)
    return (
        profile_menu_kb(
            has_sticker=has_sticker,
            has_loss_sticker=has_loss_sticker,
            hide=hide,
        ),
        has_banner,
        has_sticker,
        has_loss_sticker,
    )


async def _show_profile_menu(
    profiles: ProfileService,
    message: Message,
    *,
    user_id: int,
    caption: str,
    kb,
    has_banner: bool,
) -> None:
    if has_banner:
        await profiles.update_card(message, caption, kb, user_id=user_id)
        return
    if message.sticker or message.animation or message.photo:
        chat_id = message.chat.id
        thread_id = message.message_thread_id
        await message.delete()
        await message.bot.send_message(
            chat_id,
            caption,
            reply_markup=kb,
            message_thread_id=thread_id,
            parse_mode="HTML",
        )
        return
    await edit_menu_message(message, caption, kb)


@router.message(Command("myprofile"))
async def cmd_myprofile(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user or not await require_general(message, container.access):
        return

    await end_trade_flow(state, container.trades)
    user_id = message.from_user.id
    display_name, username = _user_from_message(message)
    kb, has_banner, has_sticker, has_loss_sticker = await _profile_kb(container.profiles, user_id)
    caption = _profile_menu_text(
        display_name=display_name,
        username=username,
        has_banner=has_banner,
        has_sticker=has_sticker,
        has_loss_sticker=has_loss_sticker,
    )

    if has_banner:
        await container.profiles.send_card(message, caption, kb, user_id=user_id)
    else:
        await message.answer(caption, reply_markup=kb, parse_mode="HTML")


@router.callback_query(F.data == "prof:menu")
async def profile_menu(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if not callback.from_user or not callback.message:
        return
    await end_trade_flow(state, container.trades)
    user_id = callback.from_user.id
    display_name, username = _user_from_callback(callback)
    kb, has_banner, has_sticker, has_loss_sticker = await _profile_kb(container.profiles, user_id)
    caption = _profile_menu_text(
        display_name=display_name,
        username=username,
        has_banner=has_banner,
        has_sticker=has_sticker,
        has_loss_sticker=has_loss_sticker,
    )
    if await answer_if_unchanged(callback, caption, kb):
        return
    await _show_profile_menu(
        container.profiles,
        callback.message,
        user_id=user_id,
        caption=caption,
        kb=kb,
        has_banner=has_banner,
    )
    await callback.answer()


async def _preview_sticker(
    callback: CallbackQuery,
    *,
    media: tuple[str, str] | None,
    caption: str,
    alert_label: str,
) -> None:
    if not callback.message:
        return
    if not media:
        await callback.answer("No sticker set", show_alert=True)
        return
    file_id, kind = media
    kb = profile_preview_back_kb()
    msg = callback.message
    chat_id = msg.chat.id
    thread_id = msg.message_thread_id
    await msg.delete()
    if kind == "animation":
        await callback.bot.send_animation(
            chat_id,
            file_id,
            caption=caption,
            reply_markup=kb,
            message_thread_id=thread_id,
            parse_mode="HTML",
        )
    else:
        await callback.bot.send_sticker(
            chat_id,
            file_id,
            reply_markup=kb,
            message_thread_id=thread_id,
        )
    await callback.answer(alert_label)


@router.callback_query(F.data == "prof:preview_sticker")
async def profile_preview_sticker(callback: CallbackQuery, container: AppContainer) -> None:
    if not callback.from_user:
        return
    display_name, username = _user_from_callback(callback)
    media = await container.profiles.get_reaction_media(callback.from_user.id)
    caption = f"{_owner_line(display_name=display_name, username=username)}\n\n🔥 <b>Your epic sticker (+100%)</b>"
    await _preview_sticker(callback, media=media, caption=caption, alert_label=f"Sticker — {display_name}")


@router.callback_query(F.data == "prof:preview_loss_sticker")
async def profile_preview_loss_sticker(callback: CallbackQuery, container: AppContainer) -> None:
    if not callback.from_user:
        return
    display_name, username = _user_from_callback(callback)
    media = await container.profiles.get_loss_reaction_media(callback.from_user.id)
    caption = f"{_owner_line(display_name=display_name, username=username)}\n\n💀 <b>Your epic sticker (-100%)</b>"
    await _preview_sticker(callback, media=media, caption=caption, alert_label=f"Loss sticker — {display_name}")


@router.callback_query(F.data == "prof:banner")
async def profile_pick_banner(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if not callback.from_user or not callback.message:
        return
    display_name, username = _user_from_callback(callback)
    kb, _, _, _ = await _profile_kb(container.profiles, callback.from_user.id, hide="banner")
    prompt = _banner_prompt(display_name=display_name, username=username)
    if await answer_if_unchanged(callback, prompt, kb):
        return
    await state.set_state(ProfileStates.waiting_banner)
    await edit_menu_message(callback.message, prompt, kb)
    await callback.answer("Your banner settings")


@router.callback_query(F.data == "prof:reaction")
async def profile_pick_reaction(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if not callback.from_user or not callback.message:
        return
    display_name, username = _user_from_callback(callback)
    kb, _, _, _ = await _profile_kb(container.profiles, callback.from_user.id, hide="reaction")
    prompt = _reaction_prompt(display_name=display_name, username=username)
    if await answer_if_unchanged(callback, prompt, kb):
        return
    await state.set_state(ProfileStates.waiting_reaction)
    await edit_menu_message(callback.message, prompt, kb)
    await callback.answer("Your +100% sticker settings")


@router.callback_query(F.data == "prof:loss_reaction")
async def profile_pick_loss_reaction(callback: CallbackQuery, state: FSMContext, container: AppContainer) -> None:
    if not callback.from_user or not callback.message:
        return
    display_name, username = _user_from_callback(callback)
    kb, _, _, _ = await _profile_kb(container.profiles, callback.from_user.id, hide="loss_reaction")
    prompt = _loss_reaction_prompt(display_name=display_name, username=username)
    if await answer_if_unchanged(callback, prompt, kb):
        return
    await state.set_state(ProfileStates.waiting_loss_reaction)
    await edit_menu_message(callback.message, prompt, kb)
    await callback.answer("Your -100% sticker settings")


@router.message(StateFilter(ProfileStates.waiting_banner), F.photo)
async def profile_photo_received(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user or not message.photo or not await require_general(message, container.access):
        return

    photo = message.photo[-1]
    try:
        await container.profiles.save_profile_photo(
            message.bot, message.from_user.id, photo.file_id,
            display_name=message.from_user.full_name,
            username=message.from_user.username,
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return

    await state.clear()
    await delete_message(message)
    display_name, _ = _user_from_message(message)
    await message.answer(
        f"✅ Banner updated for {display_name}.",
        reply_markup=profile_saved_back_kb(),
    )


@router.message(StateFilter(ProfileStates.waiting_banner), F.animation | F.video)
async def profile_animation_received(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user or not await require_general(message, container.access):
        return
    file_id = message.animation.file_id if message.animation else message.video.file_id

    try:
        await container.profiles.save_profile_animation(
            message.bot, message.from_user.id, file_id,
            display_name=message.from_user.full_name,
            username=message.from_user.username,
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return

    await state.clear()
    await delete_message(message)
    await message.answer(
        f"✅ Banner updated for {message.from_user.full_name}.",
        reply_markup=profile_saved_back_kb(),
    )


@router.message(StateFilter(ProfileStates.waiting_banner), F.document)
async def profile_document_received(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user or not message.document or not await require_general(message, container.access):
        return

    mime = message.document.mime_type or ""
    if mime not in ("image/gif", "video/mp4", "video/webm"):
        await message.answer("Send a photo or GIF.\n\nTap ◀ Back on the message above to return.")
        return

    try:
        await container.profiles.save_profile_animation(
            message.bot, message.from_user.id, message.document.file_id,
            display_name=message.from_user.full_name,
            username=message.from_user.username,
        )
    except ValueError as e:
        await message.answer(f"❌ {e}")
        return

    await state.clear()
    await delete_message(message)
    await message.answer(
        f"✅ Banner updated for {message.from_user.full_name}.",
        reply_markup=profile_saved_back_kb(),
    )


@router.message(StateFilter(ProfileStates.waiting_banner))
async def profile_banner_other(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user or not await require_general(message, container.access):
        return
    if message.text and message.text.startswith("/"):
        return
    await message.answer("Send a photo or GIF.\n\nTap ◀ Back on the message above to return.")


async def _save_reaction(
    message: Message,
    state: FSMContext,
    profiles: ProfileService,
    file_id: str,
    kind: str,
    *,
    loss: bool = False,
) -> None:
    try:
        save = profiles.save_loss_reaction_sticker if loss else profiles.save_reaction_sticker
        await save(
            message.from_user.id,  # type: ignore[union-attr]
            file_id,
            kind=kind,
            display_name=message.from_user.full_name,  # type: ignore[union-attr]
            username=message.from_user.username,  # type: ignore[union-attr]
        )
    except Exception:
        log.exception("Failed to save reaction for user %s", message.from_user.id)
        await message.answer("❌ Could not save. Try again or send another file.")
        return

    await state.clear()
    await delete_message(message)
    label = "Epic loss sticker" if loss else "Epic sticker"
    await message.answer(
        f"✅ {label} saved for {message.from_user.full_name}.",  # type: ignore[union-attr]
        reply_markup=profile_saved_back_kb(),
    )


@router.message(StateFilter(ProfileStates.waiting_reaction))
async def profile_reaction_media(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user or not await require_general(message, container.access):
        return
    if message.text and message.text.startswith("/"):
        return

    if message.sticker:
        await _save_reaction(message, state, container.profiles, message.sticker.file_id, "sticker")
        return
    if message.animation:
        await _save_reaction(message, state, container.profiles, message.animation.file_id, "animation")
        return
    if message.video:
        await _save_reaction(message, state, container.profiles, message.video.file_id, "animation")
        return
    if message.document:
        mime = message.document.mime_type or ""
        if mime.startswith("image/") or mime.startswith("video/"):
            await _save_reaction(message, state, container.profiles, message.document.file_id, "animation")
            return

    await message.answer(
        "Send a <b>sticker</b> (from a pack) or <b>GIF</b>.\n\nTap ◀ Back on the message above to return.",
    )


@router.message(StateFilter(ProfileStates.waiting_loss_reaction))
async def profile_loss_reaction_media(message: Message, state: FSMContext, container: AppContainer) -> None:
    if not message.from_user or not await require_general(message, container.access):
        return
    if message.text and message.text.startswith("/"):
        return

    if message.sticker:
        await _save_reaction(message, state, container.profiles, message.sticker.file_id, "sticker", loss=True)
        return
    if message.animation:
        await _save_reaction(message, state, container.profiles, message.animation.file_id, "animation", loss=True)
        return
    if message.video:
        await _save_reaction(message, state, container.profiles, message.video.file_id, "animation", loss=True)
        return
    if message.document:
        mime = message.document.mime_type or ""
        if mime.startswith("image/") or mime.startswith("video/"):
            await _save_reaction(message, state, container.profiles, message.document.file_id, "animation", loss=True)
            return

    await message.answer(
        "Send a <b>sticker</b> (from a pack) or <b>GIF</b>.\n\nTap ◀ Back on the message above to return.",
    )
