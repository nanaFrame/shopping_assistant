"""AnswerGenerate — streams Markdown answer token-by-token via SSE."""

from __future__ import annotations

import logging

from app.agent.state import AgentState
from app.application.stream_service import stream_service

log = logging.getLogger(__name__)


async def answer_generate(state: AgentState) -> dict:
    sid = state["session_id"]
    tid = state["turn_id"]
    stid = state["stream_id"]
    recommended = state.get("recommended_products") or []
    candidates = state.get("candidate_products") or []
    intent = state.get("intent") or {}
    warnings = list(state.get("warnings") or [])
    errors = list(state.get("errors") or [])

    log.info("  [answer_generate] recommended=%d candidates=%d errors=%d",
             len(recommended), len(candidates), len(errors))

    if not recommended and not candidates:
        msg = _no_results_message(intent, errors)
        log.info("  [answer_generate] no results -> %s", msg[:80])
        stream_service.emit_text_chunk(stid, sid, tid, msg)
        stream_service.emit_stream_done(stid, sid, tid)
        return {"final_answer": {"intro_text": msg}}

    stream_service.emit_status(stid, sid, tid, "answering", "Generating answer...")

    enrichment = state.get("enrichment_plan") or {}
    enriched_products = _merge_enrichment(recommended, enrichment)

    full_text = ""
    try:
        from app.integrations.llm.gateway import llm_gateway
        async for chunk in llm_gateway.answer_summarize_stream(
            recommended_products=enriched_products,
            user_requirements=state.get("user_requirements") or {},
            hard_constraints=state.get("hard_constraints") or {},
            soft_preferences=state.get("soft_preferences") or {},
        ):
            full_text += chunk
            stream_service.emit_text_chunk(stid, sid, tid, chunk)
    except Exception:
        log.exception("LLM answer stream failed, using template fallback")
        if not full_text:
            full_text = _template_fallback(recommended)
            stream_service.emit_text_chunk(stid, sid, tid, full_text)

    for w in warnings:
        stream_service.emit_warning(stid, sid, tid, w.get("message", ""))

    stream_service.emit_stream_done(stid, sid, tid)

    return {
        "final_answer": {
            "intro_text": full_text,
        }
    }


def _merge_enrichment(products: list[dict], enrichment: dict) -> list[dict]:
    """Merge feature_bullets, spec_highlights, description from enrichment into products."""
    completed = enrichment.get("completed", {})
    merged = []
    for p in products:
        out = dict(p)
        ref = p.get("product_ref", "")
        patches = completed.get(ref, {})
        if isinstance(patches, dict):
            for key in ("feature_bullets", "spec_highlights", "description_full", "brand", "variations"):
                if patches.get(key):
                    out[key] = patches[key]
        merged.append(out)
    return merged


def _no_results_message(intent: dict, errors: list) -> str:
    if errors:
        return "Sorry, I encountered an issue while searching. Please try again or adjust your query."
    intent_type = intent.get("intent_type", "discovery")
    if intent_type == "targeted":
        return "I couldn't find detailed information for that product. Could you provide more context?"
    return "I didn't find matching products. Try broadening your search or adjusting your criteria."


def _template_fallback(recommended: list[dict]) -> str:
    lines = ["Based on your requirements, here are my top picks:\n"]
    for i, p in enumerate(recommended, 1):
        title = p.get("title", "Product")
        price = p.get("price_current", "N/A")
        currency = p.get("currency", "$")
        lines.append(f"## {i}. {title}\n")
        lines.append(f"- **Price**: {currency} {price}\n")
        badge = p.get("badge", "")
        if badge:
            lines.append(f"- **Badge**: {badge}\n")
        lines.append("")
    lines.append("**Next steps:** Ask me to compare specific features or find alternatives.")
    return "\n".join(lines)
