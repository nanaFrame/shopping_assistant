"""Stream emitters — write into stream_state for StreamService to pick up.

StreamCandidates / StreamTop3 / StreamEnrich only write stream_state;
they never produce SSE envelopes directly.
"""

from __future__ import annotations

import logging

from app.agent.state import AgentState
from app.application.stream_service import stream_service

log = logging.getLogger(__name__)


async def stream_candidates(state: AgentState) -> dict:
    """Notify that candidates are found (cards are only emitted for Top 3)."""
    sid = state["session_id"]
    tid = state["turn_id"]
    stid = state["stream_id"]
    count = len(state.get("candidate_products") or [])

    stream_service.emit_status(
        stid, sid, tid, "candidate_ready",
        f"Found {count} candidates, scoring...",
    )

    return {
        "stream_state": {"phase": "candidate_ready", "pending_emits": []},
    }


async def stream_top3(state: AgentState) -> dict:
    """Emit Top 3 cards immediately (comparison table comes from LLM Markdown)."""
    sid = state["session_id"]
    tid = state["turn_id"]
    stid = state["stream_id"]
    recommended = state.get("recommended_products") or []

    stream_service.emit_status(stid, sid, tid, "top3_ready", "Here are the top picks")

    for card in recommended:
        stream_service.emit_top3_card(stid, sid, tid, card)

    return {
        "stream_state": {"phase": "top3_ready", "pending_emits": []},
    }


async def stream_enrich(state: AgentState) -> dict:
    """Emit enrichment patches into the event stream."""
    sid = state["session_id"]
    tid = state["turn_id"]
    stid = state["stream_id"]

    enrichment = state.get("enrichment_plan") or {}
    completed = enrichment.get("completed", {})
    log.info("  [stream_enrich] %d products with enrichment data", len(completed))

    for ref, patches in completed.items():
        if isinstance(patches, dict):
            sellers = patches.get("seller_summary")
            reviews = patches.get("review_summary")
            log.info("  [stream_enrich] ref=%s sellers=%s reviews_samples=%s keys=%s",
                     ref[:30],
                     len(sellers) if isinstance(sellers, list) else sellers,
                     len(reviews.get("sample_reviews", [])) if isinstance(reviews, dict) else reviews,
                     list(patches.keys()))
            stream_service.emit_product_patch(
                stid, sid, tid, ref, patches,
                source_stage=patches.get("_source", "product_info"),
            )

    return {
        "stream_state": {"phase": "enriching", "pending_emits": []},
    }
