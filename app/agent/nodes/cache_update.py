"""CacheUpdate — persists candidate/enrichment data to the local cache."""

from __future__ import annotations

from datetime import datetime, timezone

from app.agent.state import AgentState
from app.storage.cache_store import cache_store


async def cache_update_candidates(state: AgentState) -> dict:
    """Save base cards from ProductSearch into the cache."""
    candidates = state.get("candidate_products") or []
    for c in candidates:
        ref = c.get("product_ref", "")
        if not ref:
            continue
        cache_store.update_segment(ref, "base_card", c, freshness_key="base_card_at")
        ids = {
            k: c[k]
            for k in ("product_id", "gid", "data_docid")
            if c.get(k)
        }
        if ids:
            cache_store.update_identifiers(ref, ids)
    return {}


async def cache_update_enrich(state: AgentState) -> dict:
    """Save enrichment results into the cache (handled inline by detail_fetch)."""
    return {}
