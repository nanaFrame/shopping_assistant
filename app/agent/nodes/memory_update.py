"""MemoryUpdate — persists query snapshot and updates product catalog."""

from __future__ import annotations

from app.agent.state import AgentState
from app.application.session_service import session_service


async def memory_update(state: AgentState) -> dict:
    query_plan = state.get("query_plan")
    recommended = state.get("recommended_products") or []
    catalog = list(state.get("product_catalog") or [])
    recommendation_history = list(state.get("recommendation_history") or [])

    # Update mentioned products with newly recommended refs
    mentioned = list(state.get("mentioned_products") or [])
    for p in recommended:
        ref = p.get("product_ref", "")
        if ref and ref not in mentioned:
            mentioned.append(ref)

    # Build session summary snippet
    summary_parts = []
    if state.get("session_summary"):
        summary_parts.append(state["session_summary"])
    if recommended:
        titles = [p.get("title", "") for p in recommended[:3]]
        summary_parts.append(f"Recommended: {', '.join(titles)}")
    new_summary = " | ".join(summary_parts)[-2000:]

    if recommended:
        recommendation_history.append({
            "turn": len(recommendation_history) + 1,
            "turn_id": state.get("turn_id"),
            "keyword": (query_plan or {}).get("keyword", ""),
            "products": [
                {
                    "rank": idx,
                    "product_ref": p.get("product_ref", ""),
                    "title": p.get("title", ""),
                    "price": p.get("price_current"),
                    "currency": p.get("currency"),
                }
                for idx, p in enumerate(recommended[:3], start=1)
                if p.get("product_ref")
            ],
        })
        recommendation_history = recommendation_history[-5:]

    # Persist to session store
    session_id = state.get("session_id", "")
    if session_id:
        await session_service.save_session_state(session_id, {
            "session_summary": new_summary,
            "mentioned_products": mentioned,
            "product_catalog": catalog[-50:],
            "recommendation_history": recommendation_history,
            "last_query": query_plan,
        })

    return {
        "last_query": query_plan,
        "mentioned_products": mentioned,
        "recommendation_history": recommendation_history,
        "session_summary": new_summary,
    }
