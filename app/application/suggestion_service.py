"""Prompt suggestion generation for the test page."""

from __future__ import annotations

import logging

from app.application.suggestion_pool import related_suggestions, sample_suggestions
from app.application.session_service import session_service
from app.integrations.llm.gateway import llm_gateway

log = logging.getLogger(__name__)


class SuggestionService:
    async def get_suggestions(
        self,
        *,
        count: int = 6,
        locale: str = "en-US",
        session_id: str | None = None,
        seed_query: str | None = None,
    ) -> list[dict[str, str]]:
        if not seed_query:
            return sample_suggestions(count)

        session_summary = ""
        if session_id:
            try:
                state = await session_service.load_session_state(session_id) or {}
                session_summary = state.get("session_summary", "")
            except Exception:
                log.exception("Failed to load session summary for suggestions: %s", session_id)

        try:
            suggestions = await llm_gateway.prompt_suggestions(
                count=count,
                locale=locale,
                seed_query=seed_query,
                session_summary=session_summary,
            )
            return suggestions[:count]
        except Exception:
            log.exception("Falling back to local suggestion pool")
            return related_suggestions(seed_query, count)


suggestion_service = SuggestionService()
