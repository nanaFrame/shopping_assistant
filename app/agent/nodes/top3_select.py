"""Top3Select — picks Top 3 with differentiated badges."""

from __future__ import annotations

import logging

from app.agent.state import AgentState
from app.config import get_settings

log = logging.getLogger(__name__)


async def top3_select(state: AgentState) -> dict:
    candidates = state.get("candidate_products") or []
    top_n = get_settings().agent.top_n

    sorted_candidates = sorted(
        candidates, key=lambda x: x.get("score", 0), reverse=True
    )
    top3 = sorted_candidates[:top_n]

    badges = ["Best Overall", "Best Value", "Feature Pick"]
    for i, item in enumerate(top3):
        item["rank"] = i + 1
        item["badge"] = badges[i] if i < len(badges) else None

    log.info("  [top3_select] selected %d from %d candidates:", len(top3), len(candidates))
    for p in top3:
        log.info("    #%d [%s] %s | score=%.2f | $%s",
                 p.get("rank", 0), p.get("badge", ""),
                 p.get("title", "?")[:45],
                 p.get("score", 0),
                 p.get("price_current", "?"))

    return {"recommended_products": top3}
