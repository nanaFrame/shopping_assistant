from __future__ import annotations

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.application.suggestion_service import suggestion_service
from app.application.session_service import session_service
from app.domain.events import ApiResponse

router = APIRouter()


class PromptSuggestionsRequest(BaseModel):
    count: int = Field(default=6, ge=1, le=8)
    locale: str = "en-US"
    session_id: str | None = None
    seed_query: str | None = None


@router.post("/api/prompt-suggestions")
async def prompt_suggestions(body: PromptSuggestionsRequest):
    seed_query = (body.seed_query or "").strip() or None

    if seed_query and len(seed_query) > 4000:
        return ApiResponse.fail(
            "INVALID_ARGUMENT",
            "seed_query too long (max 4000)",
            details={"field": "seed_query"},
        ).model_dump()

    if body.session_id:
        session = await session_service.get_session(body.session_id)
        if session is None:
            return ApiResponse.fail(
                "SESSION_NOT_FOUND",
                f"Session {body.session_id} does not exist",
            ).model_dump()

    suggestions = await suggestion_service.get_suggestions(
        count=body.count,
        locale=body.locale,
        session_id=body.session_id,
        seed_query=seed_query,
    )
    return ApiResponse.success({"suggestions": suggestions}).model_dump()
