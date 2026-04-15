"""LangGraph state graph — 15-node shopping agent topology.

Topology follows langgraph-topology.md section 5.2.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from langgraph.graph import StateGraph, START, END

from app.agent.state import AgentState
from app.agent.conditions import (
    route_after_cache_read,
    route_after_search,
    route_after_score,
    route_after_enrichment,
)
from app.agent.nodes.context_merge import context_merge
from app.agent.nodes.intent_parse import intent_parse
from app.agent.nodes.query_build import query_build
from app.agent.nodes.local_cache_read import local_cache_read
from app.agent.nodes.product_search import product_search
from app.agent.nodes.product_context_resolve import product_context_resolve
from app.agent.nodes.candidate_score import candidate_score
from app.agent.nodes.top3_select import top3_select
from app.agent.nodes.stream_emitters import (
    stream_candidates,
    stream_top3,
    stream_enrich,
)
from app.agent.nodes.detail_fetch import detail_fetch
from app.agent.nodes.cache_update import cache_update_candidates, cache_update_enrich
from app.agent.nodes.answer_generate import answer_generate
from app.agent.nodes.memory_update import memory_update
from app.application.stream_service import stream_service

log = logging.getLogger(__name__)


def build_graph() -> StateGraph:
    g = StateGraph(AgentState)

    # ── Register nodes ────────────────────────────────────────
    g.add_node("context_merge", context_merge)
    g.add_node("intent_parse", intent_parse)
    g.add_node("query_build", query_build)
    g.add_node("local_cache_read", local_cache_read)
    g.add_node("product_search", product_search)
    g.add_node("stream_candidates", stream_candidates)
    g.add_node("cache_update_candidates", cache_update_candidates)
    g.add_node("product_context_resolve", product_context_resolve)
    g.add_node("candidate_score", candidate_score)
    g.add_node("top3_select", top3_select)
    g.add_node("stream_top3", stream_top3)
    g.add_node("detail_fetch", detail_fetch)
    g.add_node("cache_update_enrich", cache_update_enrich)
    g.add_node("stream_enrich", stream_enrich)
    g.add_node("answer_generate", answer_generate)
    g.add_node("memory_update", memory_update)

    # ── Main-line edges ───────────────────────────────────────
    g.add_edge(START, "context_merge")
    g.add_edge("context_merge", "intent_parse")
    g.add_edge("intent_parse", "query_build")
    g.add_edge("query_build", "local_cache_read")

    # LocalCacheRead -> branch
    g.add_conditional_edges(
        "local_cache_read",
        route_after_cache_read,
        {
            "answer_generate": "answer_generate",
            "product_context_resolve": "product_context_resolve",
            "product_search": "product_search",
        },
    )

    # ProductSearch -> branch
    g.add_conditional_edges(
        "product_search",
        route_after_search,
        {
            "fan_out_candidates": "stream_candidates",
            "product_context_resolve": "product_context_resolve",
            "answer_generate": "answer_generate",
        },
    )

    # Fan-out after search success: stream + cache update converge
    g.add_edge("stream_candidates", "cache_update_candidates")
    g.add_edge("cache_update_candidates", "product_context_resolve")

    # Scoring chain
    g.add_edge("product_context_resolve", "candidate_score")

    g.add_conditional_edges(
        "candidate_score",
        route_after_score,
        {
            "top3_select": "top3_select",
            "answer_generate": "answer_generate",
        },
    )

    g.add_edge("top3_select", "stream_top3")

    # Enrichment decision
    g.add_conditional_edges(
        "stream_top3",
        route_after_enrichment,
        {
            "detail_fetch": "detail_fetch",
            "answer_generate": "answer_generate",
        },
    )

    g.add_edge("detail_fetch", "cache_update_enrich")
    g.add_edge("cache_update_enrich", "stream_enrich")
    g.add_edge("stream_enrich", "answer_generate")

    # Final
    g.add_edge("answer_generate", "memory_update")
    g.add_edge("memory_update", END)

    return g


# Compiled graph singleton
_compiled = None


def get_compiled_graph():
    global _compiled
    if _compiled is None:
        _compiled = build_graph().compile()
    return _compiled


async def run_agent_graph(
    session_id: str,
    turn_id: str,
    stream_id: str,
    message: str,
    context: dict[str, Any] | None = None,
) -> None:
    """Execute the full agent graph for one user turn."""
    graph = get_compiled_graph()

    # Emit initial status
    stream_service.emit_status(stream_id, session_id, turn_id, "searching", "Analyzing your request...")

    # Load persisted session state
    from app.application.session_service import session_service as sess_svc
    persisted = await sess_svc.load_session_state(session_id) or {}

    initial_state: AgentState = {
        "session_id": session_id,
        "turn_id": turn_id,
        "stream_id": stream_id,
        "user_message": message,
        "context": context,
        "messages": persisted.get("messages", []),
        "session_summary": persisted.get("session_summary", ""),
        "user_requirements": persisted.get("user_requirements", {}),
        "hard_constraints": persisted.get("hard_constraints", {}),
        "soft_preferences": persisted.get("soft_preferences", {}),
        "mentioned_products": persisted.get("mentioned_products", []),
        "last_query": persisted.get("last_query"),
        "product_catalog": persisted.get("product_catalog", []),
        "recommendation_history": persisted.get("recommendation_history", []),
        "product_field_registry": {},
        "cache_refs": {},
        "candidate_products": [],
        "recommended_products": [],
        "enrichment_plan": {},
        "stream_state": {"phase": "searching", "pending_emits": []},
        "warnings": [],
        "errors": [],
        "final_answer": None,
        "followup_target_product": None,
        "intent": {},
        "query_plan": {},
        "_is_comparison": False,
    }

    # Execute with node-level timing
    node_timings: dict[str, float] = {}
    t_start = time.monotonic()

    async for event in graph.astream(initial_state, stream_mode="updates"):
        for node_name, _update in event.items():
            elapsed = time.monotonic() - t_start
            node_timings[node_name] = round(elapsed, 3)
            log.info(
                "Node [%s] completed at %.3fs (session=%s, stream=%s)",
                node_name, elapsed, session_id, stream_id,
            )

    total = round(time.monotonic() - t_start, 3)
    log.info(
        "Agent graph completed in %.3fs for stream=%s | timings=%s",
        total, stream_id, node_timings,
    )
