"""Unified LLM gateway — calls role-configured chat models."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from app.config import get_settings
from app.integrations.llm.provider_factory import resolve_role_model
from app.integrations.llm.prompts import (
    SYSTEM_PROMPT,
    INTENT_PARSE_PROMPT,
    QUERY_BUILD_PROMPT,
    CANDIDATE_SCORE_PROMPT,
    REASON_GENERATE_PROMPT,
    ANSWER_SUMMARIZE_PROMPT,
    ANSWER_STREAM_PROMPT,
    COMPARISON_STREAM_PROMPT,
    PROMPT_SUGGESTIONS_PROMPT,
)
from app.integrations.llm.validators import (
    parse_json_response,
    validate_intent_output,
    validate_query_build_output,
    validate_score_output,
    validate_reason_output,
    validate_answer_output,
    validate_prompt_suggestions_output,
)

log = logging.getLogger(__name__)


def _format_recommendation_history(history: list[dict[str, Any]] | None) -> str:
    entries = history or []
    if not entries:
        return "None"

    lines: list[str] = []
    for item in entries[-5:]:
        turn = item.get("turn", "?")
        keyword = item.get("keyword") or ""
        header = f"Turn {turn}"
        if keyword:
            header += f" | keyword: {keyword}"
        lines.append(header)
        for product in item.get("products") or []:
            rank = product.get("rank", "?")
            title = product.get("title") or "Unknown product"
            ref = product.get("product_ref") or ""
            price = product.get("price")
            currency = product.get("currency") or ""
            price_part = f" | price: {currency} {price}" if price is not None else ""
            lines.append(f"- #{rank} {title} | ref: {ref}{price_part}")
    return "\n".join(lines)


async def _call_model(
    model_type: str, prompt: str, max_retries: int | None = None
) -> dict[str, Any]:
    cfg = get_settings()
    retries = max_retries if max_retries is not None else cfg.llm.max_retries
    resolved = resolve_role_model(model_type)

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]

    log.info(
        "  [LLM] calling %s via %s (%s) prompt_len=%d",
        model_type,
        resolved.provider,
        resolved.model_name,
        len(prompt),
    )

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await resolved.chat_model.ainvoke(messages)
            text = resolved.adapter.extract_text(response)
            log.info("  [LLM] %s response_len=%d (attempt %d)", model_type, len(text), attempt + 1)
            log.debug("  [LLM] raw text: %s", text[:500])
            parsed = parse_json_response(text)
            log.info("  [LLM] %s parsed OK, keys=%s", model_type, list(parsed.keys())[:8])
            return parsed
        except Exception as e:
            last_error = e
            log.warning("  [LLM] %s attempt %d/%d failed: %s", model_type, attempt + 1, retries + 1, e)
    raise RuntimeError(f"LLM call failed after {retries + 1} attempts: {last_error}")


async def _stream_model(
    model_type: str, prompt: str, system_prompt: str = SYSTEM_PROMPT
) -> AsyncIterator[str]:
    """Stream tokens from an LLM. Yields text chunks as they arrive."""
    resolved = resolve_role_model(model_type)

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]

    log.info(
        "  [LLM] streaming %s via %s (%s) prompt_len=%d",
        model_type,
        resolved.provider,
        resolved.model_name,
        len(prompt),
    )

    total_len = 0
    async for chunk in resolved.chat_model.astream(messages):
        text = resolved.adapter.extract_chunk_text(chunk)
        if text:
            total_len += len(text)
            yield text

    log.info("  [LLM] stream %s complete, total_len=%d", model_type, total_len)


class LlmGateway:
    """High-level LLM interface for the five task types."""

    async def intent_parse(
        self,
        message: str,
        session_summary: str = "",
        mentioned_products: list[str] | None = None,
        recommendation_history: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        prompt = INTENT_PARSE_PROMPT.format(
            message=message,
            session_summary=session_summary,
            mentioned_products=json.dumps(mentioned_products or []),
            recommendation_history=_format_recommendation_history(recommendation_history),
        )
        result = await _call_model("fast", prompt)
        return validate_intent_output(result)

    async def query_build_assist(
        self,
        message: str,
        intent_type: str,
        hard_constraints: dict[str, Any],
        soft_preferences: dict[str, Any],
        last_query: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        prompt = QUERY_BUILD_PROMPT.format(
            message=message,
            intent_type=intent_type,
            hard_constraints=json.dumps(hard_constraints),
            soft_preferences=json.dumps(soft_preferences),
            last_query=json.dumps(last_query) if last_query else "null",
        )
        result = validate_query_build_output(await _call_model("fast", prompt))
        return {
            "query_mode": result.get("query_mode", intent_type),
            "keyword": result.get("keyword", message),
            "filters": {
                **(result.get("must_filters") or {}),
                **(result.get("optional_filters") or {}),
            },
            "required_fields": ["title", "price_current", "image_url"],
            "target_product_ref": result.get("followup_target_hint"),
        }

    async def candidate_score(
        self,
        candidates: list[dict[str, Any]],
        user_requirements: dict[str, Any],
        hard_constraints: dict[str, Any],
        soft_preferences: dict[str, Any],
    ) -> list[dict[str, Any]]:
        light_candidates = []
        for c in candidates:
            lc = {
                k: c.get(k)
                for k in (
                    "product_ref", "title", "brand", "price_current", "currency",
                    "seller_name", "domain", "product_rating_value", "reviews_count",
                )
            }
            desc = c.get("description_excerpt") or ""
            if desc:
                lc["description"] = desc
            light_candidates.append(lc)
        prompt = CANDIDATE_SCORE_PROMPT.format(
            user_requirements=json.dumps(user_requirements),
            hard_constraints=json.dumps(hard_constraints),
            soft_preferences=json.dumps(soft_preferences),
            candidates=json.dumps(light_candidates, indent=2),
        )
        result = await _call_model("fast", prompt)
        known_refs = {c.get("product_ref", "") for c in candidates}
        validated = validate_score_output(result, known_refs)

        score_map = {
            s["product_ref"]: s for s in validated.get("scored_candidates", [])
        }
        for c in candidates:
            ref = c.get("product_ref", "")
            if ref in score_map:
                entry = score_map[ref]
                c["score"] = entry.get("score", 0.5)
                c["matched_constraints"] = entry.get("matched_constraints", [])
                c["tradeoffs"] = entry.get("tradeoffs", [])
                c["recommended_role"] = entry.get("recommended_role", "none")
                c["role_reason"] = entry.get("role_reason", "")
        candidates.sort(key=lambda x: x.get("score", 0), reverse=True)
        return candidates

    async def reason_generate(
        self,
        recommended_products: list[dict[str, Any]],
        user_requirements: dict[str, Any],
        hard_constraints: dict[str, Any],
        enrichment_data: dict[str, Any] | None = None,
    ) -> dict[str, dict[str, Any]]:
        light_products = [
            {
                k: p.get(k)
                for k in (
                    "product_ref", "title", "brand", "price_current", "currency",
                    "product_rating_value", "reviews_count", "badge",
                    "feature_bullets", "spec_highlights",
                )
            }
            for p in recommended_products
        ]
        prompt = REASON_GENERATE_PROMPT.format(
            user_requirements=json.dumps(user_requirements),
            hard_constraints=json.dumps(hard_constraints),
            products=json.dumps(light_products, indent=2),
            enrichment_data=json.dumps(enrichment_data or {}),
        )
        result = await _call_model("quality", prompt)
        known_refs = {p.get("product_ref", "") for p in recommended_products}
        validated = validate_reason_output(result, known_refs)

        reasons: dict[str, dict[str, Any]] = {}
        for r in validated.get("reasons", []):
            reasons[r["product_ref"]] = {
                "full_reason": r.get("full_reason", ""),
                "short_reason": r.get("short_reason", ""),
                "evidence": r.get("evidence", []),
                "risk_notes": r.get("risk_notes", []),
            }
        return reasons

    async def answer_summarize(
        self,
        recommended_products: list[dict[str, Any]],
        user_requirements: dict[str, Any],
        hard_constraints: dict[str, Any],
        soft_preferences: dict[str, Any],
        enrichment_plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        light_products = [
            {
                k: p.get(k)
                for k in (
                    "product_ref", "title", "brand", "price_current",
                    "badge", "rank",
                )
            }
            for p in recommended_products
        ]
        prompt = ANSWER_SUMMARIZE_PROMPT.format(
            products=json.dumps(light_products, indent=2),
            user_requirements=json.dumps(user_requirements),
            hard_constraints=json.dumps(hard_constraints),
            soft_preferences=json.dumps(soft_preferences),
        )
        result = await _call_model("quality", prompt)
        return validate_answer_output(result)

    async def answer_summarize_stream(
        self,
        recommended_products: list[dict[str, Any]],
        user_requirements: dict[str, Any],
        hard_constraints: dict[str, Any],
        soft_preferences: dict[str, Any],
    ) -> AsyncIterator[str]:
        """Stream Markdown answer token-by-token."""
        light_products = []
        for p in recommended_products:
            lp: dict[str, Any] = {
                k: p.get(k)
                for k in (
                    "product_ref", "title", "brand", "price_current", "currency",
                    "product_rating_value", "reviews_count", "badge", "rank",
                    "seller_name",
                )
            }
            if p.get("feature_bullets"):
                lp["features"] = p["feature_bullets"][:8]
            if p.get("spec_highlights"):
                specs = p["spec_highlights"]
                lp["specs"] = dict(list(specs.items())[:10]) if isinstance(specs, dict) else specs
            if p.get("description_full"):
                lp["description"] = p["description_full"][:500]
            light_products.append(lp)
        prompt = ANSWER_STREAM_PROMPT.format(
            products=json.dumps(light_products, indent=2),
            user_requirements=json.dumps(user_requirements),
            hard_constraints=json.dumps(hard_constraints),
            soft_preferences=json.dumps(soft_preferences),
        )
        async for chunk in _stream_model("quality", prompt):
            yield chunk

    async def comparison_stream(
        self,
        message: str,
        products: list[dict[str, Any]],
        user_requirements: dict[str, Any],
        hard_constraints: dict[str, Any],
        soft_preferences: dict[str, Any],
    ) -> AsyncIterator[str]:
        light_products = []
        for p in products:
            lp: dict[str, Any] = {
                k: p.get(k)
                for k in (
                    "product_ref", "title", "brand", "price_current", "currency",
                    "product_rating_value", "reviews_count", "badge", "rank",
                    "seller_name", "domain", "description_full", "feature_bullets",
                    "spec_highlights", "seller_summary", "review_summary",
                )
            }
            if p.get("description_excerpt") and not lp.get("description_full"):
                lp["description_excerpt"] = p["description_excerpt"]
            light_products.append(lp)

        prompt = COMPARISON_STREAM_PROMPT.format(
            message=message,
            products=json.dumps(light_products, indent=2),
            user_requirements=json.dumps(user_requirements),
            hard_constraints=json.dumps(hard_constraints),
            soft_preferences=json.dumps(soft_preferences),
        )
        async for chunk in _stream_model("quality", prompt):
            yield chunk

    async def prompt_suggestions(
        self,
        *,
        count: int = 6,
        locale: str = "en-US",
        seed_query: str | None = None,
        session_summary: str = "",
    ) -> list[dict[str, str]]:
        prompt = PROMPT_SUGGESTIONS_PROMPT.format(
            count=count,
            locale=locale,
            seed_query=json.dumps(seed_query) if seed_query else "null",
            session_summary=json.dumps(session_summary or ""),
        )
        result = await _call_model("suggestion", prompt)
        return validate_prompt_suggestions_output(result, count)


llm_gateway = LlmGateway()
