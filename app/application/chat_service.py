"""Chat turn orchestration — creates turn/stream and launches the agent."""

from __future__ import annotations

import logging
from typing import Any

from app.application.session_service import session_service
from app.application.sidebar_enrichment_service import sidebar_enrichment_service
from app.domain.events import StreamEvent, EventEntity, EventMeta
from app.storage.event_buffer import event_buffer

log = logging.getLogger(__name__)


class ChatService:
    async def start_turn(
        self,
        session_id: str,
        message: str,
        context: dict[str, Any] | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[str, str]:
        """Create turn + stream ids and prepare the event buffer."""
        turn_id = session_service.new_turn_id()
        stream_id = session_service.new_stream_id()
        event_buffer.create_stream(stream_id, session_id, turn_id)
        sidebar_enrichment_service.create_stream(stream_id, session_id, turn_id)
        return turn_id, stream_id

    async def run_agent(
        self,
        session_id: str,
        turn_id: str,
        stream_id: str,
        message: str,
        context: dict[str, Any] | None,
    ) -> None:
        """Execute the LangGraph agent and feed events into the buffer.

        Phase 1 implementation emits a simple status -> stream_done sequence.
        Replaced by real agent execution in Phase 3+.
        """
        log.info("=== Agent START === session=%s stream=%s message=%r", session_id, stream_id, message[:120])
        try:
            from app.agent.graph import run_agent_graph

            await run_agent_graph(
                session_id=session_id,
                turn_id=turn_id,
                stream_id=stream_id,
                message=message,
                context=context,
            )
            log.info("=== Agent END (success) === stream=%s", stream_id)
        except Exception:
            log.exception("=== Agent END (FAILED) === stream=%s", stream_id)
            sidebar_enrichment_service.cancel_stream(stream_id)
            seq = event_buffer.next_seq(stream_id)
            error_event = StreamEvent(
                stream_id=stream_id,
                session_id=session_id,
                turn_id=turn_id,
                seq=seq,
                type="error",
                phase="failed",
                entity=EventEntity(kind="stream", id=stream_id),
                meta=EventMeta(source_stage="system"),
                payload={"message": "Internal agent error"},
            )
            event_buffer.append(stream_id, error_event.model_dump())
            event_buffer.mark_done(stream_id)


chat_service = ChatService()
