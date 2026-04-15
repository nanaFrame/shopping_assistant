"""AgentState definition for the LangGraph shopping agent."""

from __future__ import annotations

from typing import Any, TypedDict


class StreamState(TypedDict, total=False):
    phase: str
    pending_emits: list[dict[str, Any]]


class AgentState(TypedDict, total=False):
    # Session context
    messages: list[dict[str, Any]]
    session_summary: str
    user_requirements: dict[str, Any]
    hard_constraints: dict[str, Any]
    soft_preferences: dict[str, Any]

    # Intent & query
    intent: dict[str, Any]
    query_plan: dict[str, Any]
    last_query: dict[str, Any] | None

    # Product tracking
    mentioned_products: list[str]
    followup_target_product: str | None
    product_catalog: list[dict[str, Any]]
    recommendation_history: list[dict[str, Any]]
    product_field_registry: dict[str, dict[str, bool]]
    cache_refs: dict[str, str]

    # Candidates & recommendations
    candidate_products: list[dict[str, Any]]
    recommended_products: list[dict[str, Any]]
    enrichment_plan: dict[str, Any]

    # Stream output
    stream_state: StreamState

    # Internal routing flags (set by nodes, read by conditions)
    _search_ok: bool
    _candidates_count: int
    _cache_can_answer: bool
    _stale_cache_usable: bool
    _scorable_candidates: int
    _is_comparison: bool

    # Diagnostics
    warnings: list[dict[str, Any]]
    errors: list[dict[str, Any]]
    final_answer: dict[str, Any] | None

    # Runtime identifiers (injected by runner)
    session_id: str
    turn_id: str
    stream_id: str
    user_message: str
    context: dict[str, Any] | None
