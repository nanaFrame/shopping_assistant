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
