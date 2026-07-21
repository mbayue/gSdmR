"""Database connection management, schema initialization, and seed data.

Uses a singleton connection pattern with WAL mode for better concurrency.
The shared connection is created on startup and closed on shutdown.
"""

from __future__ import annotations

import aiosqlite
import bcrypt

from config import (
    DB_PATH,
    DEFAULT_ADMIN_USERNAME,
    DEFAULT_ADMIN_PASSWORD,
    DEFAULT_API_KEY,
)

# SQL schema definitions
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    base_url TEXT NOT NULL,
    api_key TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS model_providers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    model_id INTEGER NOT NULL,
    provider_id INTEGER NOT NULL,
    provider_model TEXT NOT NULL DEFAULT '',
    priority INTEGER NOT NULL,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    FOREIGN KEY (provider_id) REFERENCES providers(id) ON DELETE CASCADE,
    UNIQUE(model_id, provider_id),
    UNIQUE(model_id, priority)
);

CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    username TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_value TEXT NOT NULL UNIQUE,
    name TEXT NOT NULL,
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS api_key_models (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id INTEGER NOT NULL,
    model_id INTEGER NOT NULL,
    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE,
    FOREIGN KEY (model_id) REFERENCES models(id) ON DELETE CASCADE,
    UNIQUE(api_key_id, model_id)
);

CREATE TABLE IF NOT EXISTS usage_logs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    api_key_id INTEGER NOT NULL,
    model_name TEXT NOT NULL,
    provider_name TEXT,
    endpoint TEXT NOT NULL,
    status_code INTEGER NOT NULL,
    latency_ms INTEGER NOT NULL,
    prompt_tokens INTEGER DEFAULT 0,
    completion_tokens INTEGER DEFAULT 0,
    total_tokens INTEGER DEFAULT 0,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    FOREIGN KEY (api_key_id) REFERENCES api_keys(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_usage_logs_api_key ON usage_logs(api_key_id);
CREATE INDEX IF NOT EXISTS idx_usage_logs_created_at ON usage_logs(created_at);
CREATE INDEX IF NOT EXISTS idx_usage_logs_model ON usage_logs(model_name);
"""

# Default providers to seed on first run
DEFAULT_PROVIDERS = [
    {"name": "bluesminds", "base_url": "https://api.bluesminds.com/v1", "api_key": "sk-yLmkgOMpH4qdK1bnGHxN7oICTv9cYvCfu4PEX1fuvZvC4ABJ"},
    {"name": "freemodel", "base_url": "https://api.freemodel.dev/v1", "api_key": "fe_oa_4562ef11a983fab9aecfa66cc93989b78a16ee25262f83e5"},
    {"name": "forge-gateway", "base_url": "https://forge-gateway-api.fly.dev/v1", "api_key": "fg-20b6fff1454248cf934963c7b7b3ad81"},
    {"name": "iamhc", "base_url": "https://api.iamhc.cn/v1", "api_key": "sk-ItRgKuQLekrGvntZiVRYtpiDsSCYTMKjORUHK7dy6NVaqcDg"},
]


# Shared connection singleton
_db: aiosqlite.Connection | None = None


async def get_db() -> aiosqlite.Connection:
    """Get the shared database connection.

    Returns the singleton connection. Callers should NOT close this —
    it's managed by the app lifespan.
    """
    global _db
    if _db is None:
        _db = await aiosqlite.connect(DB_PATH)
        _db.row_factory = aiosqlite.Row
        await _db.execute("PRAGMA foreign_keys = ON")
        await _db.execute("PRAGMA journal_mode = WAL")
        await _db.execute("PRAGMA busy_timeout = 5000")
    return _db


async def close_db() -> None:
    """Close the shared database connection. Called on app shutdown."""
    global _db
    if _db is not None:
        await _db.close()
        _db = None


async def init_db() -> None:
    """Initialize the database schema and seed default data.

    Creates all tables if they don't exist, then inserts seed data
    (providers, admin user, default API key) only if not already present.
    """
    db = await get_db()

    # Create tables
    await db.executescript(SCHEMA_SQL)
    await db.commit()

    # Seed default providers
    for provider in DEFAULT_PROVIDERS:
        await db.execute(
            """
            INSERT OR IGNORE INTO providers (name, base_url, api_key)
            VALUES (?, ?, ?)
            """,
            (provider["name"], provider["base_url"], provider["api_key"]),
        )
        await db.execute(
            """
            UPDATE providers SET api_key = ?, base_url = ?
            WHERE name = ? AND api_key = ''
            """,
            (provider["api_key"], provider["base_url"], provider["name"]),
        )

    # Seed default admin user
    password_hash = bcrypt.hashpw(
        DEFAULT_ADMIN_PASSWORD.encode("utf-8"), bcrypt.gensalt()
    ).decode("utf-8")
    await db.execute(
        """
        INSERT OR IGNORE INTO users (username, password_hash)
        VALUES (?, ?)
        """,
        (DEFAULT_ADMIN_USERNAME, password_hash),
    )

    # Seed default API key
    await db.execute(
        """
        INSERT OR IGNORE INTO api_keys (key_value, name)
        VALUES (?, ?)
        """,
        (DEFAULT_API_KEY, "default"),
    )

    await db.commit()
