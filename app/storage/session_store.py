"""SQLite-backed session store."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import aiosqlite

from app.config import get_settings

_DDL = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id   TEXT PRIMARY KEY,
    client_id    TEXT,
    metadata     TEXT,
    state_json   TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    updated_at   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS turns (
    turn_id      TEXT PRIMARY KEY,
    session_id   TEXT NOT NULL,
    stream_id    TEXT NOT NULL,
    message      TEXT NOT NULL DEFAULT '',
    context_json TEXT NOT NULL DEFAULT '{}',
    created_at   TEXT NOT NULL,
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE INDEX IF NOT EXISTS idx_turns_session ON turns(session_id);
CREATE INDEX IF NOT EXISTS idx_turns_stream  ON turns(stream_id);
"""


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class SessionStore:
    def __init__(self) -> None:
        self._db_path: str | None = None
        self._initialized = False

    async def _ensure_init(self) -> None:
        if self._initialized:
            return
        settings = get_settings()
        self._db_path = settings.storage.sqlite_path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(self._db_path) as db:
            await db.executescript(_DDL)
            await db.commit()
        self._initialized = True

    async def _conn(self) -> aiosqlite.Connection:
        await self._ensure_init()
        return aiosqlite.connect(self._db_path)  # type: ignore[arg-type]

    # ── Sessions ──────────────────────────────────────────────

    async def create_session(
        self,
        session_id: str,
        client_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        now = _now()
        async with await self._conn() as db:
            await db.execute(
                "INSERT INTO sessions (session_id, client_id, metadata, state_json, created_at, updated_at) "
                "VALUES (?, ?, ?, '{}', ?, ?)",
                (session_id, client_id, json.dumps(metadata or {}), now, now),
            )
            await db.commit()

    async def session_exists(self, session_id: str) -> bool:
        async with await self._conn() as db:
            cur = await db.execute(
                "SELECT 1 FROM sessions WHERE session_id = ?", (session_id,)
            )
            return await cur.fetchone() is not None

    async def load_session_state(self, session_id: str) -> dict[str, Any] | None:
        async with await self._conn() as db:
            cur = await db.execute(
                "SELECT state_json FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return json.loads(row[0])

    async def save_session_state(
        self, session_id: str, state: dict[str, Any]
    ) -> None:
        async with await self._conn() as db:
            await db.execute(
                "UPDATE sessions SET state_json = ?, updated_at = ? WHERE session_id = ?",
                (json.dumps(state, ensure_ascii=False), _now(), session_id),
            )
            await db.commit()

    async def get_session_meta(self, session_id: str) -> dict[str, Any] | None:
        async with await self._conn() as db:
            cur = await db.execute(
                "SELECT session_id, client_id, metadata, created_at, updated_at "
                "FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return {
                "session_id": row[0],
                "client_id": row[1],
                "metadata": json.loads(row[2] or "{}"),
                "created_at": row[3],
                "updated_at": row[4],
            }

    # ── Turns ─────────────────────────────────────────────────

    async def create_turn(
        self,
        turn_id: str,
        session_id: str,
        stream_id: str,
        message: str = "",
        context: dict[str, Any] | None = None,
    ) -> None:
        async with await self._conn() as db:
            await db.execute(
                "INSERT INTO turns (turn_id, session_id, stream_id, message, context_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (turn_id, session_id, stream_id, message, json.dumps(context or {}), _now()),
            )
            await db.commit()

    async def get_turn(self, turn_id: str) -> dict[str, Any] | None:
        async with await self._conn() as db:
            cur = await db.execute(
                "SELECT turn_id, session_id, stream_id, message, context_json, created_at "
                "FROM turns WHERE turn_id = ?",
                (turn_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return {
                "turn_id": row[0],
                "session_id": row[1],
                "stream_id": row[2],
                "message": row[3],
                "context": json.loads(row[4] or "{}"),
                "created_at": row[5],
            }

    async def get_stream_turn(self, stream_id: str) -> dict[str, Any] | None:
        async with await self._conn() as db:
            cur = await db.execute(
                "SELECT turn_id, session_id, stream_id FROM turns WHERE stream_id = ?",
                (stream_id,),
            )
            row = await cur.fetchone()
            if row is None:
                return None
            return {"turn_id": row[0], "session_id": row[1], "stream_id": row[2]}


session_store = SessionStore()
