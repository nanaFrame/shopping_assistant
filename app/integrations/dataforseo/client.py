"""Low-level HTTP client for DataForSEO API with retry and error handling."""

from __future__ import annotations

import asyncio
import base64
import logging
from typing import Any

import httpx

from app.config import get_settings

log = logging.getLogger(__name__)


class DataForSeoClient:
    def __init__(self) -> None:
        self._client: httpx.AsyncClient | None = None

    def _get_auth_header(self) -> str:
        cfg = get_settings()
        creds = f"{cfg.dataforseo_login}:{cfg.dataforseo_password}"
        return "Basic " + base64.b64encode(creds.encode()).decode()

    async def _ensure_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            cfg = get_settings()
            self._client = httpx.AsyncClient(
                base_url=cfg.dataforseo.base_url,
                timeout=httpx.Timeout(cfg.dataforseo.timeout_seconds),
                headers={
                    "Authorization": self._get_auth_header(),
                    "Content-Type": "application/json",
                },
            )
        return self._client

    async def post(
        self, path: str, payload: list[dict[str, Any]]
    ) -> dict[str, Any]:
        """Send a POST request with automatic retry."""
        cfg = get_settings()
        last_error: Exception | None = None

        log.info("    [DataForSEO] POST %s (payload items=%d)", path, len(payload))
        for attempt in range(1, cfg.dataforseo.max_retries + 2):
            try:
                client = await self._ensure_client()
                resp = await client.post(path, json=payload)
                log.info("    [DataForSEO] POST %s -> HTTP %d", path, resp.status_code)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status_code") == 20000:
                    return data
                log.warning(
                    "    [DataForSEO] non-success status %s: %s",
                    data.get("status_code"),
                    data.get("status_message"),
                )
                return data
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                log.warning(
                    "DataForSEO request attempt %d/%d failed: %s",
                    attempt,
                    cfg.dataforseo.max_retries + 1,
                    exc,
                )
                if attempt <= cfg.dataforseo.max_retries:
                    await asyncio.sleep(1.5 ** attempt)

        raise RuntimeError(f"DataForSEO request failed after retries: {last_error}")

    async def get(self, path: str) -> dict[str, Any]:
        """Send a GET request with automatic retry."""
        cfg = get_settings()
        last_error: Exception | None = None

        log.info("    [DataForSEO] GET %s", path)
        for attempt in range(1, cfg.dataforseo.max_retries + 2):
            try:
                client = await self._ensure_client()
                resp = await client.get(path)
                log.info("    [DataForSEO] GET %s -> HTTP %d", path, resp.status_code)
                resp.raise_for_status()
                data = resp.json()
                if data.get("status_code") == 20000:
                    return data
                log.warning(
                    "    [DataForSEO] GET non-success status %s: %s",
                    data.get("status_code"),
                    data.get("status_message"),
                )
                return data
            except (httpx.HTTPStatusError, httpx.RequestError) as exc:
                last_error = exc
                log.warning(
                    "DataForSEO GET attempt %d/%d failed: %s",
                    attempt,
                    cfg.dataforseo.max_retries + 1,
                    exc,
                )
                if attempt <= cfg.dataforseo.max_retries:
                    await asyncio.sleep(1.5 ** attempt)

        raise RuntimeError(f"DataForSEO GET failed after retries: {last_error}")

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()


dataforseo_client = DataForSeoClient()
