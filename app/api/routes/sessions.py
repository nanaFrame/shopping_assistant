from __future__ import annotations

from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel

from app.application.session_service import session_service
from app.domain.events import ApiResponse

router = APIRouter()


class CreateSessionRequest(BaseModel):
    session_id: str | None = None
    client_id: str | None = None
    metadata: dict[str, Any] | None = None


@router.post("/api/sessions")
async def create_session(body: CreateSessionRequest):
    if body.session_id:
        session = await session_service.get_session(body.session_id)
        if session is None:
            return ApiResponse.fail(
                "SESSION_NOT_FOUND",
                f"Session {body.session_id} does not exist",
            ).model_dump()
        return ApiResponse.success(
            {"session_id": body.session_id, "is_new": False, "expires_at": None}
        ).model_dump()

    sid = await session_service.create_session(
        client_id=body.client_id, metadata=body.metadata
    )
    return ApiResponse.success(
        {"session_id": sid, "is_new": True, "expires_at": None}
    ).model_dump()
