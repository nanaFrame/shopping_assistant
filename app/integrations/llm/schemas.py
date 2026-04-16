"""Input/output schemas for the five LLM task types."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


# ── Task 1: intent_parse ──────────────────────────────────────

class IntentParseInput(BaseModel):
    message: str
    session_summary: str = ""
    mentioned_products: list[str] = Field(default_factory=list)
    recommendation_history: list[dict[str, Any]] = Field(default_factory=list)


class IntentParseOutput(BaseModel):
    intent_type: str = "discovery"  # discovery | refinement | targeted | comparison | clarify
    user_goal: str = ""
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: dict[str, Any] = Field(default_factory=dict)
    needs_external_search: bool = True
    needs_followup_resolution: bool = False
    followup_target_hint: str | None = None
    comparison_refs: list[str] = Field(default_factory=list)
    clarification_needed: bool = False
    clarification_question: str | None = None


# ── Task 2: query_build_assist ────────────────────────────────

class QueryBuildInput(BaseModel):
    message: str
    intent_type: str
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: dict[str, Any] = Field(default_factory=dict)
    last_query: dict[str, Any] | None = None


class QueryBuildOutput(BaseModel):
    query_mode: str = "discovery"
    keyword: str = ""
    must_filters: dict[str, Any] = Field(default_factory=dict)
    optional_filters: dict[str, Any] = Field(default_factory=dict)
    query_rationale: str = ""


# ── Task 3: candidate_score ───────────────────────────────────

class CandidateScoreInput(BaseModel):
    candidates: list[dict[str, Any]]
    user_requirements: dict[str, Any] = Field(default_factory=dict)
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: dict[str, Any] = Field(default_factory=dict)


class ScoredCandidate(BaseModel):
    product_ref: str
    score: float = 0.5
    matched_constraints: list[str] = Field(default_factory=list)
    tradeoffs: list[str] = Field(default_factory=list)
    reject: bool = False


class CandidateScoreOutput(BaseModel):
    scored_candidates: list[ScoredCandidate] = Field(default_factory=list)
    ranking_confidence: str = "medium"


# ── Task 4: reason_generate ───────────────────────────────────

class ReasonInput(BaseModel):
    recommended_products: list[dict[str, Any]]
    user_requirements: dict[str, Any] = Field(default_factory=dict)
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    enrichment_data: dict[str, Any] = Field(default_factory=dict)


class ReasonItem(BaseModel):
    product_ref: str
    short_reason: str = ""
    full_reason: str = ""
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    risk_notes: list[str] = Field(default_factory=list)


class ReasonOutput(BaseModel):
    reasons: list[ReasonItem] = Field(default_factory=list)


# ── Task 5: answer_summarize ──────────────────────────────────

class AnswerSummarizeInput(BaseModel):
    recommended_products: list[dict[str, Any]]
    user_requirements: dict[str, Any] = Field(default_factory=dict)
    hard_constraints: dict[str, Any] = Field(default_factory=dict)
    soft_preferences: dict[str, Any] = Field(default_factory=dict)
    enrichment_plan: dict[str, Any] = Field(default_factory=dict)


class AnswerSummarizeOutput(BaseModel):
    intro_text: str = ""
    comparison_summary: str | None = None
    followup_hint: str = ""
    reasons: dict[str, dict[str, Any]] = Field(default_factory=dict)


# ── Task 6: prompt_suggestions ────────────────────────────────

class PromptSuggestionsInput(BaseModel):
    count: int = 6
    locale: str = "en-US"
    seed_query: str | None = None
    session_summary: str = ""


class SuggestionItem(BaseModel):
    label: str
    query: str


class PromptSuggestionsOutput(BaseModel):
    suggestions: list[SuggestionItem] = Field(default_factory=list)
