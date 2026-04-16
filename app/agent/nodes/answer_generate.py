"""AnswerGenerate — streams Markdown answer token-by-token via SSE."""

from __future__ import annotations

import logging

from app.application.sidebar_enrichment_service import sidebar_enrichment_service
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
    is_comparison = intent.get("intent_type") == "comparison"

    log.info("  [answer_generate] recommended=%d candidates=%d errors=%d",
             len(recommended), len(candidates), len(errors))

    if not recommended and not candidates:
        msg = _no_results_message(intent, errors)
        log.info("  [answer_generate] no results -> %s", msg[:80])
        stream_service.emit_text_chunk(stid, sid, tid, msg)
        stream_service.emit_status(stid, sid, tid, "answer_ready", "Completed")
        sidebar_enrichment_service.mark_answer_complete(stid)
        return {"final_answer": {"intro_text": msg}}

    status_msg = "Comparing selected products..." if is_comparison else "Generating answer..."
    stream_service.emit_status(stid, sid, tid, "answering", status_msg)

    enrichment = state.get("enrichment_plan") or {}
    enriched_products = _merge_enrichment(recommended, enrichment)
    comparison_products = candidates
    sidebar_products = comparison_products if is_comparison else recommended
    background_sidebar = sidebar_enrichment_service.start(stid, sidebar_products)

    full_text = ""
    try:
        from app.integrations.llm.gateway import llm_gateway
        if is_comparison and comparison_products:
            async for chunk in llm_gateway.comparison_stream(
                message=state.get("user_message", ""),
                products=comparison_products,
                user_requirements=state.get("user_requirements") or {},
                hard_constraints=state.get("hard_constraints") or {},
                soft_preferences=state.get("soft_preferences") or {},
            ):
                full_text += chunk
                stream_service.emit_text_chunk(stid, sid, tid, chunk)
        else:
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
            full_text = (
                _comparison_fallback(comparison_products, state.get("user_message", ""))
                if is_comparison and comparison_products
                else _template_fallback(recommended)
            )
            stream_service.emit_text_chunk(stid, sid, tid, full_text)

    for w in warnings:
        stream_service.emit_warning(stid, sid, tid, w.get("message", ""))

    ready_msg = (
        "Answer ready. Loading seller and review details..."
        if background_sidebar
        else "Completed"
    )
    stream_service.emit_status(stid, sid, tid, "answer_ready", ready_msg)
    sidebar_enrichment_service.mark_answer_complete(stid)

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
    if intent_type == "comparison":
        return "I couldn't load the previously recommended products for comparison. Please ask for recommendations first or specify the products again."
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


def _comparison_fallback(products: list[dict], message: str) -> str:
    lines = [f"I compared the selected products for: {message}\n"]
    for p in products:
        title = p.get("title", "Product")
        price = p.get("price_current", "N/A")
        currency = p.get("currency", "$")
        rating = p.get("product_rating_value", "N/A")
        lines.append(f"## {title}\n")
        lines.append(f"- **Price**: {currency} {price}\n")
        lines.append(f"- **Rating**: {rating}\n")
        if p.get("feature_bullets"):
            lines.append(f"- **Highlights**: {', '.join(p.get('feature_bullets', [])[:3])}\n")
        lines.append("")
    lines.append("## Verdict\n")
    lines.append("I have shown the key facts side by side, but some deeper comparison details may be missing because the live LLM comparison step failed.\n")
    lines.append("**Next steps:** Ask me to compare a specific dimension like cushioning, weight, or value.")
    return "\n".join(lines)
