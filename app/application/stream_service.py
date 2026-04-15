"""StreamService — translates Agent stream_state into streaming event envelopes.

The Agent writes semantic results into stream_state.pending_emits.
This service converts them into the canonical StreamEvent format
defined in streaming-event-contract.md, assigns seq numbers,
and pushes into the event_buffer.
"""

from __future__ import annotations

from typing import Any

from app.domain.events import StreamEvent, EventEntity, EventMeta
from app.storage.event_buffer import event_buffer
from app.storage.event_log import event_log


class StreamService:
    """Maps Agent domain outputs to streaming events."""

    def _persist(self, stream_id: str, evt_dict: dict[str, Any]) -> None:
        """Write event to both buffer and persistent log."""
        event_buffer.append(stream_id, evt_dict)
        event_log.log_event(stream_id, evt_dict)

    def emit_status(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        phase: str,
        message: str,
    ) -> None:
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="status",
            phase=phase,
            entity=EventEntity(kind="stream", id=stream_id),
            meta=EventMeta(source_stage="system"),
            payload={"message": message},
        )
        self._persist(stream_id, evt.model_dump())

    def emit_candidate_card(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        card: dict[str, Any],
    ) -> None:
        product_ref = card.get("product_ref", "")
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="candidate_card",
            phase="candidate_ready",
            entity=EventEntity(kind="product", id=product_ref),
            meta=EventMeta(source_stage="products", is_partial=True),
            payload=card,
        )
        self._persist(stream_id, evt.model_dump())

    def emit_top3_card(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        card: dict[str, Any],
    ) -> None:
        product_ref = card.get("product_ref", "")
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="top3_card",
            phase="top3_ready",
            entity=EventEntity(kind="product", id=product_ref),
            meta=EventMeta(source_stage="products"),
            payload=card,
        )
        self._persist(stream_id, evt.model_dump())

    def emit_intro_chunk(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        text: str,
    ) -> None:
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="intro_chunk",
            phase="top3_ready",
            entity=EventEntity(kind="stream", id=stream_id),
            meta=EventMeta(source_stage="answer_generate"),
            payload={"text": text},
        )
        self._persist(stream_id, evt.model_dump())

    def emit_text_chunk(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        text: str,
    ) -> None:
        """Emit a small Markdown text chunk for token-level streaming."""
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="text_chunk",
            phase="answering",
            entity=EventEntity(kind="stream", id=stream_id),
            meta=EventMeta(source_stage="answer_generate"),
            payload={"text": text},
        )
        self._persist(stream_id, evt.model_dump())

    def emit_product_patch(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        product_ref: str,
        patch: dict[str, Any],
        source_stage: str = "product_info",
    ) -> None:
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="product_patch",
            phase="enriching",
            entity=EventEntity(kind="product", id=product_ref),
            meta=EventMeta(source_stage=source_stage, is_partial=True),
            payload=patch,
        )
        self._persist(stream_id, evt.model_dump())

    def emit_comparison_table_init(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        table: dict[str, Any],
    ) -> None:
        table_id = table.get("table_id", "comparison_main")
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="comparison_table_init",
            phase="top3_ready",
            entity=EventEntity(kind="table", id=table_id),
            meta=EventMeta(source_stage="answer_generate"),
            payload=table,
        )
        self._persist(stream_id, evt.model_dump())

    def emit_comparison_table_patch(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        table_id: str,
        patch_rows: list[dict[str, Any]],
        source_stage: str = "product_info",
    ) -> None:
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="comparison_table_patch",
            phase="enriching",
            entity=EventEntity(kind="table", id=table_id),
            meta=EventMeta(source_stage=source_stage, is_partial=True),
            payload={"rows": patch_rows},
        )
        self._persist(stream_id, evt.model_dump())

    def emit_reason_patch(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        product_ref: str,
        reason: dict[str, Any],
    ) -> None:
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="reason_patch",
            phase="enriching",
            entity=EventEntity(kind="reason", id=product_ref),
            meta=EventMeta(source_stage="reason_generate"),
            payload=reason,
        )
        self._persist(stream_id, evt.model_dump())

    def emit_warning(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> None:
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="warning",
            phase="enriching",
            entity=EventEntity(kind="stream", id=stream_id),
            meta=EventMeta(source_stage="system"),
            payload={"message": message, **(details or {})},
        )
        self._persist(stream_id, evt.model_dump())

    def emit_stream_done(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
    ) -> None:
        seq = event_buffer.next_seq(stream_id)
        evt = StreamEvent(
            stream_id=stream_id,
            session_id=session_id,
            turn_id=turn_id,
            seq=seq,
            type="stream_done",
            phase="completed",
            entity=EventEntity(kind="stream", id=stream_id),
            meta=EventMeta(source_stage="system"),
            payload={},
        )
        self._persist(stream_id, evt.model_dump())
        event_buffer.mark_done(stream_id)


stream_service = StreamService()
