import os
from pathlib import Path
from unittest.mock import patch

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


def test_access_allows_both_configured_groups():
    access = AccessService()
    groups = _sample_groups()
    with patch("bot.services.access_service.CONFIGURED_GROUPS", groups):
        with patch("bot.services.access_service.get_group", side_effect=groups.get):
            assert access.is_allowed_chat(-1001, 999)
            assert access.is_allowed_chat(-1002, 999)
            assert not access.is_allowed_chat(-1003, 999)


def test_setups_topic_per_group():
    access = AccessService()
    groups = _sample_groups()
    with patch("bot.services.access_service.get_group", side_effect=groups.get):
        assert access.is_setups_topic(-1001, 3)
        assert not access.is_setups_topic(-1001, 1)
        assert access.is_setups_topic(-1002, 24101)
        assert not access.is_setups_topic(-1002, 1)
