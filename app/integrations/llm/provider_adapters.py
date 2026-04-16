"""Provider-specific chat model adapters."""

from __future__ import annotations

import os
from typing import Any

from app.config import (
    EndpointProviderConfig,
    GeminiProviderConfig,
    LlmRoleConfig,
    ProviderName,
    Settings,
)


def _extract_text_value(value: Any) -> list[str]:
    if isinstance(value, str):
        return [value]

    if isinstance(value, list):
        parts: list[str] = []
        for item in value:
            parts.extend(_extract_text_value(item))
        return parts

    if isinstance(value, dict):
        parts: list[str] = []
        text_value = value.get("text")
        if isinstance(text_value, str) and text_value:
            parts.append(text_value)
        elif isinstance(text_value, dict):
            parts.extend(_extract_text_value(text_value))

        content_value = value.get("content")
        if content_value is not None:
            parts.extend(_extract_text_value(content_value))

        return parts

    text_attr = getattr(value, "text", None)
    if isinstance(text_attr, str) and text_attr:
        return [text_attr]

    content_attr = getattr(value, "content", None)
    if content_attr is not None:
        return _extract_text_value(content_attr)

    return []


def _join_text(parts: list[str], *, strip: bool = True) -> str:
    if strip:
        return "\n".join(part for part in (p.strip() for p in parts) if part).strip()
    return "".join(parts)


def _resolve_api_key(env_name: str, settings: Settings) -> str:
    known = {
        "GOOGLE_API_KEY": settings.google_api_key,
        "OPENAI_API_KEY": settings.openai_api_key,
        "QWEN_API_KEY": settings.qwen_api_key,
        "KIMI_API_KEY": settings.kimi_api_key,
        "GLM_API_KEY": settings.glm_api_key,
    }
    return known.get(env_name) or os.getenv(env_name, "")


class BaseProviderAdapter:
    provider_name: ProviderName

    def build_chat_model(self, role: LlmRoleConfig, settings: Settings):
        raise NotImplementedError

    def extract_text(self, response: Any) -> str:
        return _join_text(_extract_text_value(getattr(response, "content", response)))

    def extract_chunk_text(self, chunk: Any) -> str:
        """Return raw text from a streaming chunk without stripping whitespace."""
        return _join_text(
            _extract_text_value(getattr(chunk, "content", chunk)),
            strip=False,
        )


class GeminiAdapter(BaseProviderAdapter):
    provider_name: ProviderName = "gemini"

    def build_chat_model(self, role: LlmRoleConfig, settings: Settings):
        from langchain_google_genai import ChatGoogleGenerativeAI

        provider_cfg: GeminiProviderConfig = settings.llm.providers.gemini
        kwargs: dict[str, Any] = {
            "model": role.model,
            "temperature": settings.llm.temperature,
            "timeout": settings.llm.timeout_seconds,
            "vertexai": provider_cfg.vertexai,
        }
        api_key = _resolve_api_key(provider_cfg.api_key_env, settings)
        if api_key:
            kwargs["google_api_key"] = api_key
        return ChatGoogleGenerativeAI(**kwargs)

    def extract_text(self, response: Any) -> str:
        text = getattr(response, "text", None)
        if isinstance(text, str) and text.strip():
            return text.strip()
        return super().extract_text(response)

    def extract_chunk_text(self, chunk: Any) -> str:
        text = getattr(chunk, "text", None)
        if isinstance(text, str):
            return text
        return super().extract_chunk_text(chunk)


class OpenAIAdapter(BaseProviderAdapter):
    provider_name: ProviderName = "openai"

    def build_chat_model(self, role: LlmRoleConfig, settings: Settings):
        provider_cfg = settings.llm.providers.openai
        return _build_openai_style_model(role, settings, provider_cfg)


class OpenAIStyleAdapter(BaseProviderAdapter):
    provider_name: ProviderName

    def __init__(self, provider_name: ProviderName):
        self.provider_name = provider_name

    def build_chat_model(self, role: LlmRoleConfig, settings: Settings):
        provider_cfg = getattr(settings.llm.providers, self.provider_name)
        return _build_openai_style_model(role, settings, provider_cfg)


def _build_openai_style_model(
    role: LlmRoleConfig,
    settings: Settings,
    provider_cfg: EndpointProviderConfig,
):
    from langchain_openai import ChatOpenAI

    kwargs: dict[str, Any] = {
        "model": role.model,
        "temperature": settings.llm.temperature,
        "timeout": settings.llm.timeout_seconds,
        "api_key": _resolve_api_key(provider_cfg.api_key_env, settings),
    }
    if provider_cfg.base_url:
        kwargs["base_url"] = provider_cfg.base_url
    return ChatOpenAI(**kwargs)


ADAPTERS: dict[ProviderName, BaseProviderAdapter] = {
    "gemini": GeminiAdapter(),
    "openai": OpenAIAdapter(),
    "qwen": OpenAIStyleAdapter("qwen"),
    "kimi": OpenAIStyleAdapter("kimi"),
    "glm": OpenAIStyleAdapter("glm"),
}
