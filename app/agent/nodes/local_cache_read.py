"""LocalCacheRead — checks if local cache can answer the current query."""

from __future__ import annotations

import logging

from app.agent.state import AgentState
from app.storage.cache_store import cache_store

log = logging.getLogger(__name__)


async def local_cache_read(state: AgentState) -> dict:
    query_plan = state.get("query_plan") or {}
    last_query = state.get("last_query")
    target_ref = query_plan.get("target_product_ref")
    catalog = state.get("product_catalog") or []
    intent = state.get("intent") or {}
    intent_type = intent.get("intent_type", "discovery")

    cache_hit_products: list[dict] = []
    field_coverage: dict[str, dict[str, bool]] = {}
    cache_can_answer = False
    stale_cache_usable = False

    # Targeted query on a known product
    if target_ref and intent_type == "targeted":
        entry = cache_store.get(target_ref)
        if entry and entry.get("base_card"):
            cache_hit_products.append(entry["base_card"])
            cache_can_answer = True

    # Reuse cached candidates only when keyword is exactly the same
    # and no new filters were added (refinement = new search)
    if not cache_can_answer and last_query and catalog:
        kw = query_plan.get("keyword", "").lower().strip()
        last_kw = (last_query.get("keyword") or "").lower().strip()
        cur_filters = query_plan.get("filters") or {}
        last_filters = last_query.get("filters") or {}
        same_keyword = kw and last_kw and kw == last_kw
        same_filters = cur_filters == last_filters
        if same_keyword and same_filters:
            fresh_count = sum(
                1 for item in catalog
                if cache_store.is_fresh(item.get("product_ref", ""), "base_card")
            )
            if fresh_count >= 3:
                cache_can_answer = True
                cache_hit_products = [
                    cache_store.get_segment(item["product_ref"], "base_card") or item
                    for item in catalog[:30]
                ]
                log.info("  [local_cache_read] exact keyword+filters match, reusing %d cached", len(cache_hit_products))
        else:
            log.info("  [local_cache_read] keyword or filters changed (%r->%r), forcing fresh search", last_kw, kw)

    # Check stale usability
    if not cache_can_answer and catalog:
        stale_count = sum(
            1 for item in catalog if cache_store.get(item.get("product_ref", ""))
        )
        stale_cache_usable = stale_count >= 3

    log.info("  [local_cache_read] cache_can_answer=%s stale_usable=%s hits=%d",
             cache_can_answer, stale_cache_usable, len(cache_hit_products))

    return {
        "candidate_products": cache_hit_products if cache_can_answer else (
            state.get("candidate_products") or []
        ),
        "product_field_registry": field_coverage,
        "_cache_can_answer": cache_can_answer,
        "_stale_cache_usable": stale_cache_usable,
    }
