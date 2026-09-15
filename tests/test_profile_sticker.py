import asyncio

import pytest

from bot.database.db import init_db
from bot.database.profile_repository import ProfileRepository


@pytest.fixture(scope="module")
def event_loop():
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


@pytest.mark.asyncio
async def test_save_reaction_sticker_without_banner():
    await init_db()
    repo = ProfileRepository()
    uid = 990001
    await repo.save_reaction_sticker(uid, "file_sticker", kind="sticker", display_name="Test")
    profile = await repo.get_profile(uid)
    assert profile is not None
    assert profile.reaction_sticker_file_id == "file_sticker"
    assert profile.reaction_kind == "sticker"


@pytest.mark.asyncio
async def test_save_reaction_sticker_after_banner():
    await init_db()
    repo = ProfileRepository()
    uid = 990002
    await repo.save_banner(uid, "photo", "/tmp/test.jpg", "banner_fid")
    await repo.save_reaction_sticker(uid, "file_anim", kind="animation")
    profile = await repo.get_profile(uid)
    assert profile is not None
    assert profile.reaction_sticker_file_id == "file_anim"
    assert profile.reaction_kind == "animation"
    assert profile.photo_path == "/tmp/test.jpg"


@pytest.mark.asyncio
async def test_save_loss_reaction_sticker_without_banner():
    await init_db()
    repo = ProfileRepository()
    uid = 990003
    await repo.save_loss_reaction_sticker(uid, "loss_sticker", kind="sticker", display_name="Test")
    profile = await repo.get_profile(uid)
    assert profile is not None
    assert profile.loss_reaction_sticker_file_id == "loss_sticker"
    assert profile.loss_reaction_kind == "sticker"


@pytest.mark.asyncio
async def test_save_both_reaction_stickers_independently():
    await init_db()
    repo = ProfileRepository()
    uid = 990004
    await repo.save_reaction_sticker(uid, "win_sticker", kind="sticker")
    await repo.save_loss_reaction_sticker(uid, "loss_anim", kind="animation")
    profile = await repo.get_profile(uid)
    assert profile is not None
    assert profile.reaction_sticker_file_id == "win_sticker"
    assert profile.loss_reaction_sticker_file_id == "loss_anim"
    assert profile.loss_reaction_kind == "animation"
