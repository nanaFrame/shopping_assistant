"""QueryBuild — constructs a search plan from intent and constraints."""

from __future__ import annotations

import logging

from app.agent.state import AgentState

log = logging.getLogger(__name__)


async def query_build(state: AgentState) -> dict:
    intent = state.get("intent") or {}
    intent_type = intent.get("intent_type", "discovery")
    message = state.get("user_message", "")
    hard = state.get("hard_constraints") or {}
    soft = state.get("soft_preferences") or {}

    if intent_type == "comparison" and (intent.get("comparison_refs") or []):
        query_plan = {
            "query_mode": "comparison",
            "keyword": "",
            "filters": {},
            "required_fields": [],
            "target_product_ref": None,
        }
        log.info(
            "  [query_build] comparison shortcut -> refs=%s",
            intent.get("comparison_refs") or [],
        )
        return {"query_plan": query_plan}

    try:
        from app.integrations.llm.gateway import llm_gateway
        result = await llm_gateway.query_build_assist(
            message=message,
            intent_type=intent_type,
            hard_constraints=hard,
            soft_preferences=soft,
            last_query=state.get("last_query"),
        )
        log.info("  [query_build] LLM -> keyword=%r filters=%s",
                 result.get("keyword"), result.get("filters"))
        return {"query_plan": result}
    except Exception:
        log.warning("  [query_build] LLM failed, using heuristic fallback")

    filters: dict = {}
    if hard.get("price_max"):
        filters["price_max"] = hard["price_max"]
    if hard.get("price_min"):
        filters["price_min"] = hard["price_min"]

    query_plan = {
        "query_mode": intent_type,
        "keyword": message.strip(),
        "filters": filters,
        "required_fields": ["title", "price_current", "image_url"],
        "target_product_ref": intent.get("followup_target_product"),
    }
    log.info("  [query_build] heuristic -> keyword=%r filters=%s",
             query_plan["keyword"], filters)
    return {"query_plan": query_plan}
