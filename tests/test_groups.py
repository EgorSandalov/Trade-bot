import os
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from bot.groups import GroupConfig, load_configured_groups
from bot.services.access_service import AccessService


def test_load_groups_from_env_string():
    with patch.dict(os.environ, {"GROUPS": "-1001:3:1:alpha.db;-1002:24101:1:prod.db"}, clear=False):
        groups = load_configured_groups()
    assert groups[-1001].setups_topic_id == 3
    assert groups[-1001].database_path == Path("alpha.db")
    assert groups[-1002].setups_topic_id == 24101
    assert groups[-1002].database_path == Path("prod.db")


def _sample_groups() -> dict[int, GroupConfig]:
    return {
        -1001: GroupConfig(-1001, 3, 1),
        -1002: GroupConfig(-1002, 24101, 1),
    }


@pytest.mark.asyncio
async def test_access_allows_both_configured_groups():
    access = AccessService()
    bot = MagicMock()
    groups = _sample_groups()
    with patch("bot.services.access_service.CONFIGURED_GROUPS", groups):
        with patch("bot.services.access_service.get_group", side_effect=groups.get):
            assert await access.is_allowed_chat(bot, -1001, 999)
            assert await access.is_allowed_chat(bot, -1002, 999)
            assert not await access.is_allowed_chat(bot, -1003, 999)


@pytest.mark.asyncio
async def test_private_chat_allowed_for_group_member():
    access = AccessService()
    bot = MagicMock()
    groups = _sample_groups()
    access.is_group_member = AsyncMock(return_value=True)
    with patch("bot.services.access_service.CONFIGURED_GROUPS", groups):
        assert await access.is_allowed_chat(bot, 1081923052, 1081923052)


@pytest.mark.asyncio
async def test_private_chat_denied_for_non_member():
    access = AccessService()
    bot = MagicMock()
    groups = _sample_groups()
    access.is_group_member = AsyncMock(return_value=False)
    with patch("bot.services.access_service.CONFIGURED_GROUPS", groups):
        assert not await access.is_allowed_chat(bot, 999999, 999999)


@pytest.mark.asyncio
async def test_can_use_general_in_private_for_member():
    access = AccessService()
    bot = MagicMock()
    access.is_group_member = AsyncMock(return_value=True)
    assert await access.can_use_general(bot, 42, 42, None)


@pytest.mark.asyncio
async def test_resolve_trade_chat_id_from_dm():
    access = AccessService()
    bot = MagicMock()
    groups = _sample_groups()
    access._is_member_of = AsyncMock(side_effect=lambda _b, _u, cid: cid == -1002)
    with patch("bot.services.access_service.CONFIGURED_GROUPS", groups):
        assert await access.resolve_trade_chat_id(bot, 42, 42) == -1002


def test_setups_topic_per_group():
    access = AccessService()
    groups = _sample_groups()
    with patch("bot.services.access_service.get_group", side_effect=groups.get):
        assert access.is_setups_topic(-1001, 3)
        assert not access.is_setups_topic(-1001, 1)
        assert access.is_setups_topic(-1002, 24101)
        assert not access.is_setups_topic(-1002, 1)
