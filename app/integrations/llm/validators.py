"""Validators for LLM structured outputs."""

from __future__ import annotations

import json
import logging
from typing import Any

log = logging.getLogger(__name__)


def parse_json_response(text: str) -> dict[str, Any]:
    """Extract JSON from an LLM text response, handling markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        lines = cleaned.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        cleaned = "\n".join(lines).strip()
    return json.loads(cleaned)


def validate_intent_output(data: dict[str, Any]) -> dict[str, Any]:
    valid_types = {"discovery", "refinement", "targeted", "comparison", "clarify"}
    if data.get("intent_type") not in valid_types:
        data["intent_type"] = "discovery"
    comparison_refs = data.get("comparison_refs")
    if not isinstance(comparison_refs, list):
        data["comparison_refs"] = []
    else:
        data["comparison_refs"] = [str(ref) for ref in comparison_refs if ref]
    return data


def validate_query_build_output(data: dict[str, Any]) -> dict[str, Any]:
    valid_modes = {"discovery", "refinement", "targeted"}
    if data.get("query_mode") not in valid_modes:
        data["query_mode"] = "discovery"

    if not isinstance(data.get("keyword"), str):
        data["keyword"] = ""

    must_filters = data.get("must_filters")
    if not isinstance(must_filters, dict):
        must_filters = {}
    data["must_filters"] = must_filters

    optional_filters = data.get("optional_filters")
    if not isinstance(optional_filters, dict):
        optional_filters = {}

    allowed_sort_values = {"review_score", "price_low_to_high", "price_high_to_low"}
    sort_by = optional_filters.get("sort_by")
    if sort_by is None:
        optional_filters.pop("sort_by", None)
    else:
        normalized_sort = str(sort_by).strip()
        if normalized_sort not in allowed_sort_values:
            log.warning("Dropping unsupported sort_by from query_build output: %s", sort_by)
            optional_filters.pop("sort_by", None)
        else:
            optional_filters["sort_by"] = normalized_sort

    data["optional_filters"] = optional_filters
    return data


def validate_score_output(
    data: dict[str, Any], known_refs: set[str]
) -> dict[str, Any]:
    valid = []
    for item in data.get("scored_candidates", []):
        ref = item.get("product_ref", "")
        if ref not in known_refs:
            log.warning("Score output references unknown product_ref: %s", ref)
            continue
        score = item.get("score", 0.5)
        if not (0.0 <= score <= 1.0):
            log.warning("Score out of range for %s: %s, clamping", ref, score)
            score = max(0.0, min(1.0, score))
            item["score"] = score
        valid.append(item)
    data["scored_candidates"] = valid
    return data


def validate_reason_output(
    data: dict[str, Any], known_refs: set[str]
) -> dict[str, Any]:
    valid = []
    for item in data.get("reasons", []):
        ref = item.get("product_ref", "")
        if ref not in known_refs:
            log.warning("Reason references unknown product_ref: %s", ref)
            continue
        valid.append(item)
    data["reasons"] = valid
    return data


def validate_answer_output(data: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(data.get("intro_text"), str):
        data["intro_text"] = ""
    return data


def validate_prompt_suggestions_output(
    data: dict[str, Any], requested_count: int
) -> list[dict[str, str]]:
    valid: list[dict[str, str]] = []
    seen_queries: set[str] = set()

    for item in data.get("suggestions", []):
        if not isinstance(item, dict):
            continue

        label = str(item.get("label", "")).strip()
        query = str(item.get("query", "")).strip()
        if not label or not query:
            continue

        dedupe_key = query.casefold()
        if dedupe_key in seen_queries:
            continue

        seen_queries.add(dedupe_key)
        valid.append(
            {
                "label": label[:60],
                "query": query[:240],
            }
        )

        if len(valid) >= requested_count:
            break

    if not valid:
        raise ValueError("No valid prompt suggestions returned from LLM")

    return valid
