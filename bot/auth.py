from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

DB_PATH = Path("data/users.db")


async def init_db() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            CREATE TABLE IF NOT EXISTS authenticated_users (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                authenticated_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        await db.commit()
    logger.info("Auth DB initialized at %s", DB_PATH)


async def is_authenticated(user_id: int) -> bool:
    async with aiosqlite.connect(DB_PATH) as db:
        async with db.execute(
            "SELECT 1 FROM authenticated_users WHERE user_id = ?", (user_id,)
        ) as cursor:
            row = await cursor.fetchone()
            return row is not None


async def authenticate_user(user_id: int, username: str | None) -> None:
    async with aiosqlite.connect(DB_PATH) as db:
        await db.execute(
            """
            INSERT OR REPLACE INTO authenticated_users (user_id, username)
            VALUES (?, ?)
            """,
            (user_id, username or ""),
        )
        await db.commit()
    logger.info("User %s (%s) authenticated", user_id, username)
