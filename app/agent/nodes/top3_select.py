"""Top3Select — picks Top 3 with differentiated badges via role-aware selection."""

from __future__ import annotations

import logging

from app.agent.state import AgentState
from app.config import get_settings

log = logging.getLogger(__name__)

_ROLE_ORDER = ["best_overall", "best_value", "feature_pick"]
_ROLE_BADGE = {
    "best_overall": "Best Overall",
    "best_value": "Best Value",
    "feature_pick": "Feature Pick",
}


async def top3_select(state: AgentState) -> dict:
    candidates = state.get("candidate_products") or []
    top_n = get_settings().agent.top_n

    top3 = _select_by_role(candidates, top_n)

    log.info("  [top3_select] selected %d from %d candidates:", len(top3), len(candidates))
    for p in top3:
        log.info("    #%d [%s] %s | score=%.2f | $%s | role=%s",
                 p.get("rank", 0), p.get("badge", ""),
                 p.get("title", "?")[:45],
                 p.get("score", 0),
                 p.get("price_current", "?"),
                 p.get("recommended_role", "none"))

    return {"recommended_products": top3}


def _select_by_role(candidates: list[dict], top_n: int) -> list[dict]:
    role_map: dict[str, dict] = {}
    for c in candidates:
        role = c.get("recommended_role", "none")
        if role in _ROLE_ORDER and role not in role_map:
            role_map[role] = c

    selected: list[dict] = []
    used_refs: set[str] = set()

    if len(role_map) == len(_ROLE_ORDER):
        for role in _ROLE_ORDER:
            item = role_map[role]
            selected.append(item)
            used_refs.add(item.get("product_ref", ""))
        log.info("  [top3_select] role-based selection successful")
    else:
        log.info("  [top3_select] incomplete roles (%s), falling back to score-based",
                 list(role_map.keys()))
        sorted_candidates = sorted(
            candidates, key=lambda x: x.get("score", 0), reverse=True
        )
        selected = sorted_candidates[:top_n]

    fallback_badges = ["Best Overall", "Best Value", "Feature Pick"]
    for i, item in enumerate(selected[:top_n]):
        item["rank"] = i + 1
        role = item.get("recommended_role", "none")
        item["badge"] = _ROLE_BADGE.get(role) or (fallback_badges[i] if i < len(fallback_badges) else None)

    return selected[:top_n]
