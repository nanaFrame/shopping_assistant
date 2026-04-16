"""Factory for resolving role-based provider models."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from app.config import LlmRoleConfig, ProviderName, Settings, get_settings
from app.integrations.llm.provider_adapters import ADAPTERS, BaseProviderAdapter


@dataclass
class ResolvedProviderModel:
    role_name: str
    provider: ProviderName
    model_name: str
    adapter: BaseProviderAdapter
    chat_model: Any


_RESOLVED_MODELS: dict[str, ResolvedProviderModel] = {}


def _get_role_config(role_name: str, settings: Settings) -> LlmRoleConfig:
    if role_name == "quality":
        return settings.llm.quality
    if role_name == "suggestion":
        return settings.llm.suggestion_role
    return settings.llm.fast


def resolve_role_model(role_name: str) -> ResolvedProviderModel:
    cached = _RESOLVED_MODELS.get(role_name)
    if cached is not None:
        return cached

    settings = get_settings()
    role_cfg = _get_role_config(role_name, settings)
    adapter = ADAPTERS.get(role_cfg.provider)
    if adapter is None:
        raise ValueError(f"Unsupported LLM provider: {role_cfg.provider}")

    resolved = ResolvedProviderModel(
        role_name=role_name,
        provider=role_cfg.provider,
        model_name=role_cfg.model,
        adapter=adapter,
        chat_model=adapter.build_chat_model(role_cfg, settings),
    )
    _RESOLVED_MODELS[role_name] = resolved
    return resolved
