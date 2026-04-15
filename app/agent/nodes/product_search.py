"""ProductSearch — searches DataForSEO Products endpoint for candidates."""

from __future__ import annotations

import logging

from app.agent.state import AgentState

log = logging.getLogger(__name__)


async def product_search(state: AgentState) -> dict:
    query_plan = state.get("query_plan") or {}
    keyword = query_plan.get("keyword", state.get("user_message", ""))
    filters = query_plan.get("filters") or {}

    log.info("  [product_search] keyword=%r filters=%s", keyword, filters)
    try:
        from app.integrations.dataforseo.gateway import dataforseo_gateway
        candidates = await dataforseo_gateway.search_products(
            keyword=keyword,
            filters=filters,
        )
        catalog_additions = [
            {"product_ref": c.get("product_ref"), "title": c.get("title")}
            for c in candidates
        ]

        log.info("  [product_search] OK -> %d candidates found", len(candidates))
        if candidates:
            for c in candidates[:3]:
                log.info("    - %s | %s | %s",
                         c.get("product_ref", "?")[:30],
                         c.get("title", "?")[:50],
                         c.get("price_current"))

        return {
            "candidate_products": candidates,
            "product_catalog": (state.get("product_catalog") or []) + catalog_additions,
            "_search_ok": True,
            "_candidates_count": len(candidates),
        }
    except Exception as exc:
        log.exception("  [product_search] FAILED: %s", exc)
        return {
            "candidate_products": [],
            "_search_ok": False,
            "_candidates_count": 0,
            "errors": (state.get("errors") or []) + [
                {"stage": "product_search", "message": str(exc)}
            ],
        }
