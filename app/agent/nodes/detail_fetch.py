"""DetailFetch — blocking product_info enrichment for Top 3 products."""

from __future__ import annotations

import asyncio
import logging

from app.agent.state import AgentState
from app.config import get_settings

log = logging.getLogger(__name__)


async def detail_fetch(state: AgentState) -> dict:
    recommended = state.get("recommended_products") or []
    registry = dict(state.get("product_field_registry") or {})
    settings = get_settings()
    timeout = settings.agent.detail_fetch_timeout_seconds
    max_concurrent = settings.agent.max_concurrent_fetches

    enrichment_plan: dict = {"needed": {}, "completed": {}, "failed": {}}
    semaphore = asyncio.Semaphore(max_concurrent)

    from app.integrations.dataforseo.gateway import dataforseo_gateway
    from app.storage.cache_store import cache_store

    product_ids = []
    for p in recommended:
        ref = p.get("product_ref", "")
        ids = _extract_ids(p, ref)
        product_ids.append((ref, ids))

    async def _fetch_product_info(ref: str, ids: dict) -> tuple[str, str, dict | None]:
        if not (ids.get("product_id") or ids.get("gid") or ids.get("data_docid")):
            return ref, "product_info", None
        async with semaphore:
            try:
                info = await dataforseo_gateway.get_product_info(ids)
                if info:
                    cache_store.update_segment(
                        ref, "product_info_snapshot", info,
                        freshness_key="product_info_at",
                    )
                return ref, "product_info", info
            except Exception as e:
                log.warning("Product info fetch failed for %s: %s", ref, e)
                return ref, "product_info", None

    all_tasks: list[asyncio.Task] = []
    for ref, ids in product_ids:
        all_tasks.append(asyncio.create_task(_fetch_product_info(ref, ids)))

    log.info("  [detail_fetch] launching %d product_info requests for %d products",
             len(all_tasks), len(recommended))

    done, pending = await asyncio.wait(all_tasks, timeout=timeout)
    if pending:
        log.warning(
            "DetailFetch timed out after %ds; preserving %d completed tasks and cancelling %d pending tasks",
            timeout,
            len(done),
            len(pending),
        )
        for task in pending:
            task.cancel()
        await asyncio.gather(*pending, return_exceptions=True)

    results = [task.result() for task in done if not task.cancelled()]

    for result in results:
        if isinstance(result, Exception):
            log.warning("Detail fetch task error: %s", result)
            continue
        ref, endpoint, data = result
        if data is None:
            continue

        patches = enrichment_plan["completed"].setdefault(ref, {})
        if endpoint == "product_info":
            patches.update(data)

    for ref, patches in enrichment_plan["completed"].items():
        registry.setdefault(ref, {}).update({
            k: True for k in patches if not k.startswith("_")
        })

    return {
        "enrichment_plan": enrichment_plan,
        "product_field_registry": registry,
    }


def _extract_ids(product: dict, ref: str) -> dict:
    ids: dict = {}
    if product.get("product_id"):
        ids["product_id"] = product["product_id"]
    elif "pid:" in ref:
        ids["product_id"] = ref.split("pid:")[-1]
    if product.get("gid"):
        ids["gid"] = product["gid"]
    if product.get("data_docid"):
        ids["data_docid"] = product["data_docid"]
    return ids
