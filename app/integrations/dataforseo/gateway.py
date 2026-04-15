"""DataForSEO unified gateway — wraps the four Google Shopping endpoints."""

from __future__ import annotations

import logging
from typing import Any

from app.config import get_settings
from app.integrations.dataforseo.client import dataforseo_client
from app.integrations.dataforseo.mappers import (
    map_products_response,
    map_product_info_response,
    map_sellers_response,
    map_reviews_response,
)

log = logging.getLogger(__name__)


class DataForSeoGateway:
    """High-level interface to DataForSEO Google Shopping endpoints."""

    # ── Products (search) ─────────────────────────────────────

    async def search_products(
        self,
        keyword: str,
        filters: dict[str, Any] | None = None,
        location_code: int = 2840,
        language_code: str | None = None,
    ) -> list[dict[str, Any]]:
        cfg = get_settings()
        lang = language_code or cfg.dataforseo.default_language
        f = filters or {}

        task: dict[str, Any] = {
            "keyword": keyword,
            "location_code": location_code,
            "language_code": lang,
        }
        if f.get("depth"):
            task["depth"] = f["depth"]
        if f.get("price_min") is not None:
            task["price_min"] = f["price_min"]
        if f.get("price_max") is not None:
            task["price_max"] = f["price_max"]
        if f.get("sort_by"):
            task["sort_by"] = f["sort_by"]
        if f.get("search_param"):
            task["search_param"] = f["search_param"]

        path = "/merchant/google/products/task_post"
        log.info("  [DataForSEO] search_products keyword=%r location=%d lang=%s", keyword, location_code, lang)
        data = await dataforseo_client.post(path, [task])
        task_id = _extract_task_id(data)
        if not task_id:
            log.error("  [DataForSEO] No task_id returned from task_post")
            raise RuntimeError("No task_id from Products task_post")

        log.info("  [DataForSEO] task_id=%s, polling for results...", task_id)
        result_path = f"/merchant/google/products/task_get/advanced/{task_id}"
        result = await _poll_task(result_path)

        raw_items = _extract_items(result)
        log.info("  [DataForSEO] search_products -> %d raw items", len(raw_items))
        mapped = map_products_response(raw_items)
        log.info("  [DataForSEO] search_products -> %d mapped products", len(mapped))
        return mapped

    # ── Product Info ──────────────────────────────────────────

    async def get_product_info(
        self, ids: dict[str, str]
    ) -> dict[str, Any] | None:
        task = _build_id_task(ids)
        if not task:
            return None

        path = "/merchant/google/product_info/task_post"
        data = await dataforseo_client.post(path, [task])
        task_id = _extract_task_id(data)
        if not task_id:
            return None

        result_path = f"/merchant/google/product_info/task_get/advanced/{task_id}"
        result = await _poll_task(result_path)
        items = _extract_items(result)
        if not items:
            return None
        return map_product_info_response(items[0])

    # ── Sellers ───────────────────────────────────────────────

    async def get_sellers(
        self, ids: dict[str, str]
    ) -> list[dict[str, Any]] | None:
        task = _build_id_task(ids)
        if not task:
            return None

        path = "/merchant/google/sellers/task_post"
        data = await dataforseo_client.post(path, [task])
        task_id = _extract_task_id(data)
        if not task_id:
            return None

        result_path = f"/merchant/google/sellers/task_get/advanced/{task_id}"
        result = await _poll_task(result_path)
        tasks = result.get("tasks") or []
        if not tasks:
            return None
        results = tasks[0].get("result") or []
        if not results:
            return None
        seller_items = results[0].get("items") or []
        log.info("  [DataForSEO] get_sellers -> %d seller items", len(seller_items))
        return map_sellers_response(seller_items)

    # ── Reviews ───────────────────────────────────────────────

    async def get_reviews(self, gid: str) -> dict[str, Any] | None:
        if not gid:
            return None

        task: dict[str, Any] = {
            "gid": gid,
            "location_code": 2840,
            "language_code": get_settings().dataforseo.default_language,
        }

        path = "/merchant/google/reviews/task_post"
        data = await dataforseo_client.post(path, [task])
        task_id = _extract_task_id(data)
        if not task_id:
            return None

        result_path = f"/merchant/google/reviews/task_get/advanced/{task_id}"
        result = await _poll_task(result_path)
        tasks = result.get("tasks") or []
        if not tasks:
            return None
        results = tasks[0].get("result") or []
        if not results:
            return None
        review_data = results[0]
        log.info("  [DataForSEO] get_reviews -> reviews_count=%s, items=%d",
                 review_data.get("reviews_count"), len(review_data.get("items") or []))
        return map_reviews_response(review_data)


# ── Internal helpers ──────────────────────────────────────────

def _extract_task_id(data: dict) -> str | None:
    tasks = data.get("tasks") or []
    if tasks and tasks[0].get("id"):
        return tasks[0]["id"]
    return None


def _extract_items(data: dict) -> list[dict]:
    tasks = data.get("tasks") or []
    if not tasks:
        return []
    results = tasks[0].get("result") or []
    if not results:
        return []
    return results[0].get("items") or results


async def _poll_task(result_path: str, max_attempts: int = 10) -> dict:
    import asyncio
    data: dict = {}
    for i in range(max_attempts):
        data = await dataforseo_client.get(result_path)
        tasks = data.get("tasks") or []
        if tasks:
            status = tasks[0].get("status_code")
            if status == 20000:
                log.info("  [DataForSEO] poll attempt %d -> ready (20000)", i + 1)
                return data
            if status == 40602:
                log.info("  [DataForSEO] poll attempt %d -> not ready (40602), waiting %ds", i + 1, 2 * (i + 1))
                await asyncio.sleep(2 * (i + 1))
                continue
            log.warning("  [DataForSEO] poll attempt %d -> unexpected status %s", i + 1, status)
        return data
    log.warning("  [DataForSEO] poll exhausted %d attempts", max_attempts)
    return data


def _build_id_task(ids: dict[str, str]) -> dict[str, Any] | None:
    cfg = get_settings()
    task: dict[str, Any] = {
        "location_code": 2840,
        "language_code": cfg.dataforseo.default_language,
    }
    if ids.get("product_id"):
        task["product_id"] = ids["product_id"]
    elif ids.get("gid"):
        task["gid"] = ids["gid"]
    elif ids.get("data_docid"):
        task["data_docid"] = ids["data_docid"]
    else:
        return None
    return task


dataforseo_gateway = DataForSeoGateway()
