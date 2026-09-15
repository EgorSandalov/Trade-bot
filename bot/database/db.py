import aiosqlite
from contextlib import asynccontextmanager
from pathlib import Path

from bot.config import PROFILES_DATABASE_PATH
from bot.database.context import get_request_chat_id
from bot.groups import all_trade_database_paths, database_path_for_chat

TRADES_SCHEMA = """
CREATE TABLE IF NOT EXISTS trades (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id INTEGER NOT NULL,
    user_name TEXT NOT NULL,
    username TEXT,
    exchange TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    leverage INTEGER NOT NULL,
    entry_type TEXT NOT NULL,
    status TEXT NOT NULL,
    entry_price REAL NOT NULL,
    executed_entry_price REAL,
    remaining_percent REAL NOT NULL DEFAULT 100,
    comment TEXT,
    close_reason TEXT,
    result_clean_move_pct REAL,
    result_personal_move_pct REAL,
    avg_exit_price REAL,
    card_message_id INTEGER,
    card_chat_id INTEGER,
    setup_chat_id INTEGER,
    setup_message_id INTEGER,
    setup_thread_id INTEGER,
    result_points REAL,
    user_trade_number INTEGER,
    last_monitored_at TEXT,
    created_at TEXT NOT NULL,
    opened_at TEXT,
    closed_at TEXT
);

CREATE TABLE IF NOT EXISTS take_profits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    order_index INTEGER NOT NULL,
    price REAL NOT NULL,
    close_percent REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    executed_price REAL,
    executed_at TEXT,
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS stop_losses (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL UNIQUE,
    price REAL NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    executed_price REAL,
    executed_at TEXT,
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS trade_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    description TEXT NOT NULL,
    created_at TEXT NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_trades_user ON trades(user_id);
CREATE INDEX IF NOT EXISTS idx_trades_status ON trades(status);
CREATE INDEX IF NOT EXISTS idx_trades_closed ON trades(closed_at);

CREATE TABLE IF NOT EXISTS partial_exits (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    trade_id INTEGER NOT NULL,
    price REAL NOT NULL,
    close_percent REAL NOT NULL,
    closed_at TEXT NOT NULL,
    FOREIGN KEY (trade_id) REFERENCES trades(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_partial_trade ON partial_exits(trade_id);
"""

PROFILES_SCHEMA = """
CREATE TABLE IF NOT EXISTS user_profiles (
    user_id INTEGER PRIMARY KEY,
    profile_type TEXT NOT NULL DEFAULT 'photo',
    photo_path TEXT,
    telegram_file_id TEXT,
    custom_emoji_id TEXT,
    emoji_fallback TEXT,
    reaction_sticker_file_id TEXT,
    reaction_kind TEXT DEFAULT 'sticker',
    loss_reaction_sticker_file_id TEXT,
    loss_reaction_kind TEXT DEFAULT 'sticker',
    display_name TEXT,
    username TEXT,
    updated_at TEXT NOT NULL
);
"""

_MIGRATIONS = (
    "ALTER TABLE trades ADD COLUMN setup_chat_id INTEGER",
    "ALTER TABLE trades ADD COLUMN setup_message_id INTEGER",
    "ALTER TABLE trades ADD COLUMN setup_thread_id INTEGER",
    "ALTER TABLE trades ADD COLUMN result_points REAL",
    "ALTER TABLE trades ADD COLUMN user_trade_number INTEGER",
    "ALTER TABLE trades ADD COLUMN last_monitored_at TEXT",
    "ALTER TABLE stop_losses ADD COLUMN trail_mode TEXT NOT NULL DEFAULT 'fixed'",
    "ALTER TABLE stop_losses ADD COLUMN trail_value REAL",
    "ALTER TABLE stop_losses ADD COLUMN activation_price REAL",
    "ALTER TABLE stop_losses ADD COLUMN extreme_price REAL",
    "ALTER TABLE stop_losses ADD COLUMN trail_active INTEGER NOT NULL DEFAULT 0",
    "ALTER TABLE stop_losses ADD COLUMN pre_activation_stop REAL",
    "ALTER TABLE user_profiles ADD COLUMN profile_type TEXT NOT NULL DEFAULT 'photo'",
    "ALTER TABLE user_profiles ADD COLUMN telegram_file_id TEXT",
    "ALTER TABLE user_profiles ADD COLUMN custom_emoji_id TEXT",
    "ALTER TABLE user_profiles ADD COLUMN emoji_fallback TEXT",
    "ALTER TABLE user_profiles ADD COLUMN reaction_sticker_file_id TEXT",
    "ALTER TABLE user_profiles ADD COLUMN display_name TEXT",
    "ALTER TABLE user_profiles ADD COLUMN username TEXT",
    "ALTER TABLE user_profiles ADD COLUMN reaction_kind TEXT DEFAULT 'sticker'",
    "ALTER TABLE user_profiles ADD COLUMN loss_reaction_sticker_file_id TEXT",
    "ALTER TABLE user_profiles ADD COLUMN loss_reaction_kind TEXT DEFAULT 'sticker'",
)


def _resolve_trade_db_path(chat_id: int | None = None) -> Path:
    cid = chat_id if chat_id is not None else get_request_chat_id()
    return database_path_for_chat(cid)


async def init_db() -> None:
    for path in all_trade_database_paths():
        path.parent.mkdir(parents=True, exist_ok=True)
        await _init_trade_db(path)
    PROFILES_DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    await _init_profiles_db(PROFILES_DATABASE_PATH)
    await _maybe_migrate_profiles_from_trade_dbs()


async def _maybe_migrate_profiles_from_trade_dbs() -> None:
    """One-time copy of user_profiles from legacy combined trade DBs."""
    async with aiosqlite.connect(PROFILES_DATABASE_PATH) as profiles_db:
        row = await (
            await profiles_db.execute("SELECT COUNT(*) FROM user_profiles")
        ).fetchone()
        if row and row[0]:
            return
        for path in all_trade_database_paths():
            if not path.exists():
                continue
            async with aiosqlite.connect(path) as trade_db:
                trade_db.row_factory = aiosqlite.Row
                try:
                    rows = await (
                        await trade_db.execute("SELECT * FROM user_profiles")
                    ).fetchall()
                except aiosqlite.OperationalError:
                    continue
                if not rows:
                    continue
                keys = rows[0].keys()
                cols = ", ".join(keys)
                placeholders = ", ".join("?" for _ in keys)
                for row in rows:
                    await profiles_db.execute(
                        f"INSERT OR IGNORE INTO user_profiles ({cols}) VALUES ({placeholders})",
                        tuple(row[k] for k in keys),
                    )
                await profiles_db.commit()
                return


async def _init_trade_db(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(TRADES_SCHEMA)
        for col in _MIGRATIONS:
            if "user_profiles" in col:
                continue
            try:
                await db.execute(col)
            except aiosqlite.OperationalError:
                pass
        await _backfill_user_trade_numbers(db)
        await db.commit()


async def _init_profiles_db(path: Path) -> None:
    async with aiosqlite.connect(path) as db:
        await db.executescript(PROFILES_SCHEMA)
        for col in _MIGRATIONS:
            if "user_profiles" not in col and "trades" not in col and "stop_losses" not in col:
                continue
            if "user_profiles" not in col:
                continue
            try:
                await db.execute(col)
            except aiosqlite.OperationalError:
                pass
        await _migrate_user_profiles_photo_nullable(db)
        await db.commit()


async def _migrate_user_profiles_photo_nullable(db) -> None:
    row = await (
        await db.execute(
            "SELECT \"notnull\" FROM pragma_table_info('user_profiles') WHERE name='photo_path'"
        )
    ).fetchone()
    if not row or not row[0]:
        return
    await db.execute(
        """
        CREATE TABLE user_profiles_new (
            user_id INTEGER PRIMARY KEY,
            profile_type TEXT NOT NULL DEFAULT 'photo',
            photo_path TEXT,
            telegram_file_id TEXT,
            custom_emoji_id TEXT,
            emoji_fallback TEXT,
            reaction_sticker_file_id TEXT,
            reaction_kind TEXT DEFAULT 'sticker',
            loss_reaction_sticker_file_id TEXT,
            loss_reaction_kind TEXT DEFAULT 'sticker',
            display_name TEXT,
            username TEXT,
            updated_at TEXT NOT NULL
        )
        """
    )
    await db.execute(
        """
        INSERT INTO user_profiles_new (
            user_id, profile_type, photo_path, telegram_file_id,
            custom_emoji_id, emoji_fallback, reaction_sticker_file_id,
            reaction_kind, loss_reaction_sticker_file_id, loss_reaction_kind,
            display_name, username, updated_at
        )
        SELECT
            user_id,
            COALESCE(profile_type, 'photo'),
            photo_path,
            telegram_file_id,
            custom_emoji_id,
            emoji_fallback,
            reaction_sticker_file_id,
            COALESCE(reaction_kind, 'sticker'),
            loss_reaction_sticker_file_id,
            COALESCE(loss_reaction_kind, 'sticker'),
            display_name,
            username,
            updated_at
        FROM user_profiles
        """
    )
    await db.execute("DROP TABLE user_profiles")
    await db.execute("ALTER TABLE user_profiles_new RENAME TO user_profiles")


async def _backfill_user_trade_numbers(db) -> None:
    await db.execute(
        """
        UPDATE trades SET user_trade_number = (
            SELECT COUNT(*) FROM trades t2
            WHERE t2.user_id = trades.user_id AND t2.id <= trades.id
        )
        """
    )


@asynccontextmanager
async def get_connection(chat_id: int | None = None):
    path = _resolve_trade_db_path(chat_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db


@asynccontextmanager
async def get_profiles_connection():
    path = PROFILES_DATABASE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(path) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA foreign_keys = ON")
        yield db
