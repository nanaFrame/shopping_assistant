from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path
from typing import Any

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


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000
    cors_origins: list[str] = ["*"]


class LlmConfig(BaseModel):
    fast_model: str = "gemini-2.0-flash"
    quality_model: str = "gemini-2.5-pro-preview-05-06"
    temperature: float = 0.3
    max_retries: int = 2
    timeout_seconds: int = 30


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
    detail_fetch_timeout_seconds: int = 10
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


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Load config.yaml then overlay secrets from environment variables."""
    raw = _load_yaml()
    raw["dataforseo_login"] = os.getenv("DATAFORSEO_LOGIN", "")
    raw["dataforseo_password"] = os.getenv("DATAFORSEO_PASSWORD", "")
    raw["google_api_key"] = os.getenv("GOOGLE_API_KEY", "")
    return Settings(**raw)
