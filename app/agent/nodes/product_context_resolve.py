"""ProductContextResolve — resolves product context for scoring."""

from __future__ import annotations

from app.agent.state import AgentState
from app.storage.cache_store import cache_store


async def product_context_resolve(state: AgentState) -> dict:
    candidates = state.get("candidate_products") or []
    registry = dict(state.get("product_field_registry") or {})
    catalog = list(state.get("product_catalog") or [])

    enriched: list[dict] = []
    for c in candidates:
        ref = c.get("product_ref", "")
        cached = cache_store.get(ref)
        merged = dict(c)
        if cached:
            base = cached.get("base_card") or {}
            for k, v in base.items():
                if v is not None and merged.get(k) is None:
                    merged[k] = v

        enriched.append(merged)
        registry.setdefault(ref, {}).update({
            "title": bool(merged.get("title")),
            "price_current": merged.get("price_current") is not None,
            "image_url": bool(merged.get("image_url")),
            "product_rating_value": merged.get("product_rating_value") is not None,
        })

    return {
        "candidate_products": enriched,
        "product_field_registry": registry,
        "product_catalog": catalog,
    }
