"""Conditional edge functions for the LangGraph state graph."""

from __future__ import annotations

import logging

from app.agent.state import AgentState

log = logging.getLogger(__name__)


def route_after_cache_read(state: AgentState) -> str:
    if state.get("_cache_can_answer"):
        log.info("  [route] cache_read -> product_context_resolve (cache hit)")
        return "product_context_resolve"
    log.info("  [route] cache_read -> product_search (cache miss)")
    return "product_search"


def route_after_search(state: AgentState) -> str:
    search_ok = state.get("_search_ok", False)
    count = state.get("_candidates_count", 0)

    if search_ok and count > 0:
        log.info("  [route] search -> fan_out_candidates (ok, %d results)", count)
        return "fan_out_candidates"
    if search_ok and count == 0:
        log.info("  [route] search -> answer_generate (ok but 0 results)")
        return "answer_generate"
    if state.get("_stale_cache_usable"):
        log.info("  [route] search -> product_context_resolve (failed, stale cache)")
        return "product_context_resolve"
    log.info("  [route] search -> answer_generate (failed, no fallback)")
    return "answer_generate"


def route_after_score(state: AgentState) -> str:
    scorable = state.get("_scorable_candidates", 0)
    if scorable > 0:
        log.info("  [route] score -> top3_select (%d scorable)", scorable)
        return "top3_select"
    log.info("  [route] score -> answer_generate (0 scorable)")
    return "answer_generate"


def route_after_enrichment(state: AgentState) -> str:
    recommended = state.get("recommended_products") or []
    registry = state.get("product_field_registry") or {}

    needs = False
    for p in recommended:
        ref = p.get("product_ref", "")
        fields = registry.get(ref, {})
        if not fields.get("feature_bullets") or not fields.get("seller_summary"):
            needs = True
            break

    if needs:
        log.info("  [route] enrichment -> detail_fetch (missing fields)")
        return "detail_fetch"
    log.info("  [route] enrichment -> answer_generate (all fields present)")
    return "answer_generate"
