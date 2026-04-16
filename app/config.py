from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any, Literal

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel, Field

load_dotenv()

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_CONFIG_PATH = _PROJECT_ROOT / "config.yaml"


def _load_yaml() -> dict[str, Any]:
    with open(_CONFIG_PATH, encoding="utf-8") as f:
        return yaml.safe_load(f) or {}


# ── Sub-models ────────────────────────────────────────────────


ProviderName = Literal["gemini", "openai", "qwen", "kimi", "glm"]


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 6010
    cors_origins: list[str] = ["*"]


class LlmRoleConfig(BaseModel):
    provider: ProviderName = "gemini"
    model: str = ""


class GeminiProviderConfig(BaseModel):
    api_key_env: str = "GOOGLE_API_KEY"
    vertexai: bool = True
    project: str | None = None
    location: str | None = None


class EndpointProviderConfig(BaseModel):
    api_key_env: str
    base_url: str | None = None


class LlmProvidersConfig(BaseModel):
    gemini: GeminiProviderConfig = Field(default_factory=GeminiProviderConfig)
    openai: EndpointProviderConfig = Field(
        default_factory=lambda: EndpointProviderConfig(api_key_env="OPENAI_API_KEY")
    )
    qwen: EndpointProviderConfig = Field(
        default_factory=lambda: EndpointProviderConfig(
            api_key_env="QWEN_API_KEY",
            base_url="https://dashscope.aliyuncs.com/compatible-mode/v1",
        )
    )
    kimi: EndpointProviderConfig = Field(
        default_factory=lambda: EndpointProviderConfig(
            api_key_env="KIMI_API_KEY",
            base_url="https://api.moonshot.cn/v1",
        )
    )
    glm: EndpointProviderConfig = Field(
        default_factory=lambda: EndpointProviderConfig(
            api_key_env="GLM_API_KEY",
            base_url="https://open.bigmodel.cn/api/paas/v4/",
        )
    )


class LlmConfig(BaseModel):
    fast: LlmRoleConfig = Field(
        default_factory=lambda: LlmRoleConfig(
            provider="gemini",
            model="gemini-2.0-flash",
        )
    )
    quality: LlmRoleConfig = Field(
        default_factory=lambda: LlmRoleConfig(
            provider="gemini",
            model="gemini-2.5-pro-preview-05-06",
        )
    )
    suggestion: LlmRoleConfig | None = None
    providers: LlmProvidersConfig = Field(default_factory=LlmProvidersConfig)
    temperature: float = 0.3
    max_retries: int = 2
    timeout_seconds: int = 30

    @property
    def suggestion_role(self) -> LlmRoleConfig:
        return self.suggestion or self.fast


class DataForSeoConfig(BaseModel):
    base_url: str = "https://api.dataforseo.com/v3"
    timeout_seconds: int = 15
    max_retries: int = 2
    default_locale: str = "en"
    default_language: str = "en"


class CacheTtlConfig(BaseModel):
    base_card_hours: int = 24
    product_info_days: int = 7
    sellers_hours: int = 6
    reviews_days: int = 7


class CacheConfig(BaseModel):
    sqlite_path: str = "./data/cache.db"
    json_legacy_path: str = "./data/cache"
    ttl: CacheTtlConfig = CacheTtlConfig()


class StorageConfig(BaseModel):
    sqlite_path: str = "./data/sessions.db"
    event_log_path: str = "./data/events"


class StreamConfig(BaseModel):
    heartbeat_interval_seconds: int = 20
    buffer_max_events: int = 1000
    event_version: str = "v1"


class AgentConfig(BaseModel):
    max_candidates: int = 30
    top_n: int = 3
    detail_fetch_timeout_seconds: int = 45
    max_concurrent_fetches: int = 5


# ── Root settings ─────────────────────────────────────────────


class Settings(BaseModel):
    server: ServerConfig = ServerConfig()
    llm: LlmConfig = LlmConfig()
    dataforseo: DataForSeoConfig = DataForSeoConfig()
    cache: CacheConfig = CacheConfig()
    storage: StorageConfig = StorageConfig()
    stream: StreamConfig = StreamConfig()
    agent: AgentConfig = AgentConfig()

    # Secrets from .env
    dataforseo_login: str = Field(default="")
    dataforseo_password: str = Field(default="")
    google_api_key: str = Field(default="")
    openai_api_key: str = Field(default="")
    qwen_api_key: str = Field(default="")
    kimi_api_key: str = Field(default="")
    glm_api_key: str = Field(default="")


def _normalize_legacy_llm_config(raw: dict[str, Any]) -> dict[str, Any]:
    llm_raw = raw.get("llm")
    if not isinstance(llm_raw, dict):
        return raw

    if any(key in llm_raw for key in ("fast", "quality", "suggestion")):
        return raw

    legacy_fast = llm_raw.pop("fast_model", None)
    legacy_quality = llm_raw.pop("quality_model", None)
    legacy_suggestion = llm_raw.pop("suggestion_model", None)

    if not any((legacy_fast, legacy_quality, legacy_suggestion)):
        return raw

    llm_raw["fast"] = {
        "provider": "gemini",
        "model": legacy_fast or "gemini-2.0-flash",
    }
    llm_raw["quality"] = {
        "provider": "gemini",
        "model": legacy_quality or "gemini-2.5-pro-preview-05-06",
    }
    if legacy_suggestion:
        llm_raw["suggestion"] = {
            "provider": "gemini",
            "model": legacy_suggestion,
        }

    raw["llm"] = llm_raw
    return raw


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load config.yaml then overlay secrets from environment variables."""
    raw = _normalize_legacy_llm_config(_load_yaml())
    raw["dataforseo_login"] = os.getenv("DATAFORSEO_LOGIN", "")
    raw["dataforseo_password"] = os.getenv("DATAFORSEO_PASSWORD", "")
    raw["google_api_key"] = os.getenv("GOOGLE_API_KEY", "")
    raw["openai_api_key"] = os.getenv("OPENAI_API_KEY", "")
    raw["qwen_api_key"] = os.getenv("QWEN_API_KEY", "")
    raw["kimi_api_key"] = os.getenv("KIMI_API_KEY", "")
    raw["glm_api_key"] = os.getenv("GLM_API_KEY", "")
    return Settings(**raw)
