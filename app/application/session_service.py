"""Session lifecycle management — backed by SQLite."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from app.storage.session_store import session_store


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid4().hex[:16]}"


class SessionService:
    async def create_session(
        self,
        client_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> str:
        sid = _new_id("sess")
        await session_store.create_session(sid, client_id=client_id, metadata=metadata)
        return sid

    async def get_session(self, session_id: str) -> dict[str, Any] | None:
        return await session_store.get_session_meta(session_id)

    async def load_session_state(self, session_id: str) -> dict[str, Any] | None:
        return await session_store.load_session_state(session_id)

    async def save_session_state(self, session_id: str, state: dict[str, Any]) -> None:
        await session_store.save_session_state(session_id, state)

    async def create_turn(
        self,
        session_id: str,
        message: str,
        stream_id: str,
        context: dict[str, Any] | None = None,
    ) -> str:
        turn_id = _new_id("turn")
        await session_store.create_turn(
            turn_id, session_id, stream_id, message=message, context=context
        )
        return turn_id

    def new_turn_id(self) -> str:
        return _new_id("turn")

    def new_stream_id(self) -> str:
        return _new_id("stream")


session_service = SessionService()
