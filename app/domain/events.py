"""Unified response envelope and streaming event definitions."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from pydantic import BaseModel, Field


# ── Control-plane response envelope (HTTP JSON) ──────────────


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: dict[str, Any] | None = None
    retryable: bool = False


class ResponseMeta(BaseModel):
    request_id: str = Field(default_factory=lambda: f"req_{uuid4().hex[:12]}")
    server_time: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class ApiResponse(BaseModel):
    ok: bool
    data: Any | None = None
    error: ErrorDetail | None = None
    meta: ResponseMeta = Field(default_factory=ResponseMeta)

    @classmethod
    def success(cls, data: Any = None, **meta_kw: Any) -> "ApiResponse":
        return cls(ok=True, data=data, meta=ResponseMeta(**meta_kw))

    @classmethod
    def fail(
        cls,
        code: str,
        message: str,
        *,
        details: dict[str, Any] | None = None,
        retryable: bool = False,
        **meta_kw: Any,
    ) -> "ApiResponse":
        return cls(
            ok=False,
            error=ErrorDetail(
                code=code,
                message=message,
                details=details,
                retryable=retryable,
            ),
            meta=ResponseMeta(**meta_kw),
        )


# ── Streaming event envelope ─────────────────────────────────

PHASES = (
    "searching",
    "candidate_ready",
    "top3_ready",
    "enriching",
    "completed",
    "failed",
)

EVENT_TYPES = (
    "status",
    "intro_chunk",
    "candidate_card",
    "top3_card",
    "product_patch",
    "comparison_table_init",
    "comparison_table_patch",
    "reason_patch",
    "warning",
    "error",
    "stream_done",
)


class EventEntity(BaseModel):
    kind: str  # "product", "table", "reason", "stream"
    id: str


class EventMeta(BaseModel):
    source_stage: str = "system"
    is_partial: bool = False
    replace: bool = False


class StreamEvent(BaseModel):
    version: str = "v1"
    event_id: str = Field(default_factory=lambda: f"evt_{uuid4().hex[:12]}")
    stream_id: str
    session_id: str
    turn_id: str
    seq: int
    type: str
    phase: str
    entity: EventEntity
    meta: EventMeta = Field(default_factory=EventMeta)
    payload: dict[str, Any] = Field(default_factory=dict)
