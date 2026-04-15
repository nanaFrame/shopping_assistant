from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from app.application.chat_service import chat_service
from app.application.session_service import session_service
from app.domain.events import ApiResponse

log = logging.getLogger(__name__)
router = APIRouter()


class ChatOptions(BaseModel):
    stream_mode: str = "chat_then_stream"
    allow_cached_products: bool = True
    debug: bool = False


class ChatRequest(BaseModel):
    session_id: str | None = None
    message: str
    client_request_id: str | None = None
    context: dict[str, Any] | None = None
    options: ChatOptions = Field(default_factory=ChatOptions)


@router.post("/api/chat")
async def chat(body: ChatRequest, background_tasks: BackgroundTasks):
    # Validate message
    if not body.message or not body.message.strip():
        return ApiResponse.fail(
            "INVALID_ARGUMENT", "message must not be empty", details={"field": "message"}
        ).model_dump()
    if len(body.message) > 4000:
        return ApiResponse.fail(
            "INVALID_ARGUMENT",
            "message too long (max 4000)",
            details={"field": "message"},
        ).model_dump()
    if body.options.stream_mode != "chat_then_stream":
        return ApiResponse.fail(
            "UNSUPPORTED_STREAM_MODE",
            f"stream_mode '{body.options.stream_mode}' is not supported",
        ).model_dump()

    # Ensure session exists
    if body.session_id:
        sess = await session_service.get_session(body.session_id)
        if sess is None:
            return ApiResponse.fail(
                "SESSION_NOT_FOUND",
                f"Session {body.session_id} does not exist",
            ).model_dump()
        sid = body.session_id
    else:
        sid = await session_service.create_session()

    log.info(">>> Chat request: session=%s message=%r", sid, body.message[:120])

    turn_id, stream_id = await chat_service.start_turn(
        session_id=sid,
        message=body.message,
        context=body.context,
        options=body.options.model_dump(),
    )

    log.info("    Turn created: turn=%s stream=%s", turn_id, stream_id)

    stream_url = (
        f"/api/stream?session_id={sid}"
        f"&turn_id={turn_id}&stream_id={stream_id}"
    )

    background_tasks.add_task(
        chat_service.run_agent, sid, turn_id, stream_id, body.message, body.context
    )

    return ApiResponse.success(
        {
            "session_id": sid,
            "turn_id": turn_id,
            "stream_id": stream_id,
            "status": "accepted",
            "stream_url": stream_url,
            "replay_from_seq": 1,
        }
    ).model_dump()
