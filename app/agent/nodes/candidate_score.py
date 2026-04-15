"""CandidateScore — scores candidates using LLM or heuristic fallback."""

from __future__ import annotations

import logging

from app.agent.state import AgentState

log = logging.getLogger(__name__)


async def candidate_score(state: AgentState) -> dict:
    candidates = state.get("candidate_products") or []
    if not candidates:
        return {"candidate_products": [], "_scorable_candidates": 0}

    hard = state.get("hard_constraints") or {}
    soft = state.get("soft_preferences") or {}
    requirements = state.get("user_requirements") or {}

    MAX_LLM_CANDIDATES = 15
    pre_scored = _heuristic_score(list(candidates), hard)
    llm_batch = pre_scored[:MAX_LLM_CANDIDATES]
    remainder = pre_scored[MAX_LLM_CANDIDATES:]

    log.info("  [candidate_score] %d total, sending top %d to LLM (pre-scored by heuristic)",
             len(candidates), len(llm_batch))

    try:
        from app.integrations.llm.gateway import llm_gateway
        scored = await llm_gateway.candidate_score(
            candidates=llm_batch,
            user_requirements=requirements,
            hard_constraints=hard,
            soft_preferences=soft,
        )
        all_scored = scored + remainder
        scorable = len([c for c in all_scored if c.get("score") is not None])
        log.info("  [candidate_score] LLM -> %d scored, top=%s (%.2f)",
                 scorable,
                 all_scored[0].get("title", "?")[:40] if all_scored else "N/A",
                 all_scored[0].get("score", 0) if all_scored else 0)
        return {
            "candidate_products": all_scored,
            "_scorable_candidates": scorable,
        }
    except Exception:
        log.warning("  [candidate_score] LLM failed, using heuristic fallback")

    warnings = list(state.get("warnings") or [])
    warnings.append({"stage": "candidate_score", "message": "Used heuristic scoring (LLM unavailable)"})
    return {
        "candidate_products": pre_scored,
        "_scorable_candidates": len(pre_scored),
        "warnings": warnings,
    }


def _heuristic_score(candidates: list[dict], hard: dict) -> list[dict]:
    price_max = hard.get("price_max")
    scored = []
    for c in candidates:
        score = 0.5
        rating = c.get("product_rating_value")
        if rating is not None:
            score += (rating / 5.0) * 0.3

        reviews = c.get("reviews_count")
        if reviews and reviews > 100:
            score += 0.1
        if reviews and reviews > 1000:
            score += 0.1

        price = c.get("price_current")
        if price_max and price and price <= price_max:
            score += 0.1
        elif price_max and price and price > price_max:
            score -= 0.3

        c["score"] = round(min(max(score, 0), 1), 3)
        scored.append(c)

    scored.sort(key=lambda x: x.get("score", 0), reverse=True)
    return scored
