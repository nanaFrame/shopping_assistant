"""Unified LLM gateway — calls Gemini models with structured output."""

from __future__ import annotations

import json
import logging
from typing import Any, AsyncIterator

from app.config import get_settings
from app.integrations.llm.prompts import (
    SYSTEM_PROMPT,
    INTENT_PARSE_PROMPT,
    QUERY_BUILD_PROMPT,
    CANDIDATE_SCORE_PROMPT,
    REASON_GENERATE_PROMPT,
    ANSWER_SUMMARIZE_PROMPT,
    ANSWER_STREAM_PROMPT,
)
from app.integrations.llm.validators import (
    parse_json_response,
    validate_intent_output,
    validate_score_output,
    validate_reason_output,
    validate_answer_output,
)

log = logging.getLogger(__name__)

_chat_model_fast = None
_chat_model_quality = None


def _get_fast_model():
    global _chat_model_fast
    if _chat_model_fast is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        cfg = get_settings()
        _chat_model_fast = ChatGoogleGenerativeAI(
            model=cfg.llm.fast_model,
            temperature=cfg.llm.temperature,
            google_api_key=cfg.google_api_key,
            vertexai=True,
            timeout=cfg.llm.timeout_seconds,
        )
    return _chat_model_fast


def _get_quality_model():
    global _chat_model_quality
    if _chat_model_quality is None:
        from langchain_google_genai import ChatGoogleGenerativeAI
        cfg = get_settings()
        _chat_model_quality = ChatGoogleGenerativeAI(
            model=cfg.llm.quality_model,
            temperature=cfg.llm.temperature,
            google_api_key=cfg.google_api_key,
            vertexai=True,
            timeout=cfg.llm.timeout_seconds,
        )
    return _chat_model_quality


def _extract_text(response) -> str:
    """Extract plain-text from an AIMessage.

    - Gemini 3+:  .content is a list of blocks, .text returns the joined string.
    - Gemini 2.5-: .content is already a plain string.
    """
    if hasattr(response, "text") and isinstance(response.text, str) and response.text:
        return response.text

    content = getattr(response, "content", None)
    if isinstance(content, str) and content:
        return content
    if isinstance(content, list):
        parts = []
        for block in content:
            if isinstance(block, dict) and block.get("text"):
                parts.append(block["text"])
            elif isinstance(block, str):
                parts.append(block)
        if parts:
            return "\n".join(parts)

    return ""


async def _call_model(
    model_type: str, prompt: str, max_retries: int | None = None
) -> dict[str, Any]:
    cfg = get_settings()
    retries = max_retries if max_retries is not None else cfg.llm.max_retries
    model = _get_fast_model() if model_type == "fast" else _get_quality_model()

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [SystemMessage(content=SYSTEM_PROMPT), HumanMessage(content=prompt)]

    model_name = cfg.llm.fast_model if model_type == "fast" else cfg.llm.quality_model
    log.info("  [LLM] calling %s (%s) prompt_len=%d", model_type, model_name, len(prompt))

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            response = await model.ainvoke(messages)
            text = _extract_text(response)
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
    cfg = get_settings()
    model = _get_fast_model() if model_type == "fast" else _get_quality_model()

    from langchain_core.messages import SystemMessage, HumanMessage

    messages = [SystemMessage(content=system_prompt), HumanMessage(content=prompt)]

    model_name = cfg.llm.fast_model if model_type == "fast" else cfg.llm.quality_model
    log.info("  [LLM] streaming %s (%s) prompt_len=%d", model_type, model_name, len(prompt))

    total_len = 0
    async for chunk in model.astream(messages):
        text = _extract_text(chunk)
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
    ) -> dict[str, Any]:
        prompt = INTENT_PARSE_PROMPT.format(
            message=message,
            session_summary=session_summary,
            mentioned_products=json.dumps(mentioned_products or []),
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
        result = await _call_model("fast", prompt)
        return {
            "query_mode": result.get("query_mode", intent_type),
            "keyword": result.get("keyword", message),
            "filters": {
                **(result.get("must_filters") or {}),
                **(result.get("optional_filters") or {}),
            },
            "required_fields": ["title", "price_current", "image_url"],
            "target_product_ref": None,
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
                lc["description"] = desc[:300]
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
                c["score"] = score_map[ref].get("score", 0.5)
                c["matched_constraints"] = score_map[ref].get("matched_constraints", [])
                c["tradeoffs"] = score_map[ref].get("tradeoffs", [])
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


llm_gateway = LlmGateway()
