"""Multi-group configuration: chat_id + topic IDs + per-group database."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class GroupConfig:
    chat_id: int
    setups_topic_id: int | None = None
    general_topic_id: int | None = None
    database_path: Path | None = None

    @property
    def db_path(self) -> Path:
        if self.database_path:
            path = self.database_path
            return path if path.is_absolute() else _BASE_DIR / path
        return _BASE_DIR / "data" / f"trades_{abs(self.chat_id)}.db"


def _parse_group_entry(raw: str) -> GroupConfig | None:
    part = raw.strip()
    if not part:
        return None
    pieces = part.split(":")
    if not pieces or not pieces[0].lstrip("-").isdigit():
        return None
    chat_id = int(pieces[0])
    setups = int(pieces[1]) if len(pieces) > 1 and pieces[1].isdigit() else None
    general = int(pieces[2]) if len(pieces) > 2 and pieces[2].isdigit() else None
    db_path = pieces[3].strip() if len(pieces) > 3 and pieces[3].strip() else None
    return GroupConfig(
        chat_id,
        setups,
        general,
        Path(db_path) if db_path else None,
    )


def load_configured_groups() -> dict[int, GroupConfig]:
    groups: dict[int, GroupConfig] = {}
    raw = os.getenv("GROUPS", "").strip()
    if raw:
        for entry in raw.split(";"):
            cfg = _parse_group_entry(entry)
            if cfg:
                groups[cfg.chat_id] = cfg
        return groups

    chat_raw = os.getenv("GROUP_CHAT_ID", "")
    if chat_raw.lstrip("-").isdigit():
        chat_id = int(chat_raw)
        setups_raw = os.getenv("SETUPS_TOPIC_ID", "")
        general_raw = os.getenv("GENERAL_TOPIC_ID", "")
        db_raw = os.getenv("DATABASE_PATH", "trades.db").strip()
        groups[chat_id] = GroupConfig(
            chat_id,
            int(setups_raw) if setups_raw.isdigit() else None,
            int(general_raw) if general_raw.isdigit() else None,
            Path(db_raw) if db_raw else None,
        )
    return groups


CONFIGURED_GROUPS: dict[int, GroupConfig] = load_configured_groups()


def get_group(chat_id: int) -> GroupConfig | None:
    return CONFIGURED_GROUPS.get(chat_id)


def primary_group() -> GroupConfig | None:
    if not CONFIGURED_GROUPS:
        return None
    return next(iter(CONFIGURED_GROUPS.values()))


def primary_chat_id() -> int | None:
    group = primary_group()
    return group.chat_id if group else None


def setups_topic_for_chat(chat_id: int | None) -> int | None:
    if chat_id is None:
        group = primary_group()
        return group.setups_topic_id if group else None
    group = get_group(chat_id)
    return group.setups_topic_id if group else None


def database_path_for_chat(chat_id: int | None) -> Path:
    if chat_id is not None and chat_id < 0:
        group = get_group(chat_id)
        if group:
            return group.db_path
    group = primary_group()
    if group:
        return group.db_path
    default = os.getenv("DATABASE_PATH", "trades.db").strip() or "trades.db"
    path = Path(default)
    return path if path.is_absolute() else _BASE_DIR / path


def all_trade_database_paths() -> list[Path]:
    if CONFIGURED_GROUPS:
        return [g.db_path for g in CONFIGURED_GROUPS.values()]
    return [database_path_for_chat(None)]
