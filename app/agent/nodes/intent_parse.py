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

    try:
        from app.integrations.llm.gateway import llm_gateway
        result = await llm_gateway.intent_parse(
            message=message,
            session_summary=state.get("session_summary", ""),
            mentioned_products=mentioned,
        )
        log.info("  [intent_parse] LLM -> type=%s, needs_search=%s",
                 result.get("intent_type"), result.get("needs_external_search"))
        return {
            "intent": result,
        }
    except Exception:
        log.warning("  [intent_parse] LLM failed, using heuristic fallback")

    intent_type = _heuristic_intent(message, mentioned)
    log.info("  [intent_parse] heuristic -> type=%s", intent_type)
    return {
        "intent": {
            "intent_type": intent_type,
            "needs_external_search": intent_type in ("discovery", "refinement"),
            "needs_detail_fetch": intent_type == "targeted",
            "followup_target_product": None,
        },
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
