"""IntentParse — identifies user intent via LLM or rule-based fallback."""

from __future__ import annotations

import logging

from app.agent.state import AgentState

log = logging.getLogger(__name__)


async def intent_parse(state: AgentState) -> dict:
    """Classify the user message into an intent type.

    Uses LLM when available, falls back to keyword heuristics.
    """
    message = state.get("user_message", "")
    mentioned = state.get("mentioned_products") or []
    recommendation_history = state.get("recommendation_history") or []

    try:
        from app.integrations.llm.gateway import llm_gateway
        result = await llm_gateway.intent_parse(
            message=message,
            session_summary=state.get("session_summary", ""),
            mentioned_products=mentioned,
            recommendation_history=recommendation_history,
        )
        log.info(
            "  [intent_parse] LLM -> type=%s, needs_search=%s comparison_refs=%s",
            result.get("intent_type"),
            result.get("needs_external_search"),
            result.get("comparison_refs") or [],
        )
        return _build_return(result)
    except Exception:
        log.warning("  [intent_parse] LLM failed, using heuristic fallback")

    intent_type = _heuristic_intent(message, mentioned)
    comparison_refs = _heuristic_comparison_refs(message, recommendation_history)
    log.info("  [intent_parse] heuristic -> type=%s", intent_type)
    return _build_return({
        "intent_type": intent_type,
        "needs_external_search": intent_type in ("discovery", "refinement"),
        "needs_detail_fetch": intent_type == "targeted",
        "followup_target_product": None,
        "comparison_refs": comparison_refs,
    })


def _build_return(result: dict) -> dict:
    """Promote constraints extracted by LLM (or left empty by heuristic) to top-level state."""
    hard = result.get("hard_constraints") or {}
    soft = result.get("soft_preferences") or {}
    user_goal = result.get("user_goal", "")
    log.info("  [intent_parse] constraints -> hard=%s soft=%s goal=%r", hard, soft, user_goal[:80])
    return {
        "intent": result,
        "hard_constraints": hard,
        "soft_preferences": soft,
        "user_requirements": {"user_goal": user_goal, **hard, **soft},
    }


def _heuristic_intent(message: str, mentioned: list[str]) -> str:
    lower = message.lower()
    comparison_kw = ["compare", "vs", "difference", "对比", "比较", "哪个好"]
    targeted_kw = ["tell me more", "details", "这个", "详细", "具体"]
    clarify_kw = ["什么意思", "不太懂", "clarify"]

    if any(k in lower for k in comparison_kw):
        return "comparison"
    if any(k in lower for k in targeted_kw) and mentioned:
        return "targeted"
    if any(k in lower for k in clarify_kw):
        return "clarify"
    if mentioned:
        return "refinement"
    return "discovery"


def _heuristic_comparison_refs(
    message: str,
    recommendation_history: list[dict],
) -> list[str]:
    if not recommendation_history:
        return []

    lower = message.lower()
    latest_products = list((recommendation_history[-1] or {}).get("products") or [])
    if not latest_products:
        return []

    ordinal_map = [
        (("前两个", "first two", "first 2"), [1, 2]),
        (("前三个", "first three", "top 3", "top three"), [1, 2, 3]),
        (("第一个和第二个", "第一和第二", "first and second", "1 vs 2"), [1, 2]),
        (("第二个和第三个", "second and third", "2 vs 3"), [2, 3]),
        (("第一个", "first one", "first product", "1st"), [1]),
        (("第二个", "second one", "second product", "2nd"), [2]),
        (("第三个", "third one", "third product", "3rd"), [3]),
    ]
    for phrases, ranks in ordinal_map:
        if any(phrase in lower for phrase in phrases):
            refs = [
                item.get("product_ref", "")
                for item in latest_products
                if item.get("rank") in ranks and item.get("product_ref")
            ]
            if refs:
                return refs

    if any(token in lower for token in ("compare", "vs", "比较", "对比", "哪个好", "which")):
        refs = [
            item.get("product_ref", "")
            for item in latest_products[:2]
            if item.get("product_ref")
        ]
        return refs

    return []
