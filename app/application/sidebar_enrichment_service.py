"""Sidebar enrichment service for late-arriving sellers and reviews."""

from __future__ import annotations

import asyncio
import logging
import threading
from dataclasses import dataclass
from typing import Any

from app.application.stream_service import stream_service
from app.config import get_settings
from app.integrations.dataforseo.gateway import dataforseo_gateway
from app.storage.cache_store import cache_store

log = logging.getLogger(__name__)


@dataclass
class _SidebarJob:
    session_id: str
    turn_id: str
    task: asyncio.Task | None = None
    answer_complete: bool = False
    finalized: bool = False
    connections: int = 0


class SidebarEnrichmentService:
    """Runs sellers/reviews enrichment in the background while SSE stays open."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._jobs: dict[str, _SidebarJob] = {}

    def create_stream(self, stream_id: str, session_id: str, turn_id: str) -> None:
        with self._lock:
            self._jobs[stream_id] = _SidebarJob(
                session_id=session_id,
                turn_id=turn_id,
            )

    def register_connection(self, stream_id: str) -> None:
        with self._lock:
            job = self._jobs.get(stream_id)
            if job:
                job.connections += 1

    def unregister_connection(self, stream_id: str) -> None:
        task: asyncio.Task | None = None
        with self._lock:
            job = self._jobs.get(stream_id)
            if not job:
                return
            job.connections = max(job.connections - 1, 0)
            if job.connections == 0:
                task = job.task

        if task and not task.done():
            log.info("  [sidebar_enrichment] cancelling background job for disconnected stream=%s", stream_id)
            task.cancel()

    def cancel_stream(self, stream_id: str) -> None:
        task: asyncio.Task | None = None
        with self._lock:
            job = self._jobs.get(stream_id)
            if job:
                task = job.task
        if task and not task.done():
            task.cancel()

    def has_pending_work(self, stream_id: str) -> bool:
        with self._lock:
            job = self._jobs.get(stream_id)
            return bool(job and job.task and not job.task.done())

    def start(self, stream_id: str, products: list[dict[str, Any]]) -> bool:
        job = self._jobs.get(stream_id)
        if not job:
            return False

        with self._lock:
            current = self._jobs.get(stream_id)
            if current and current.task and not current.task.done():
                return True

        work_items = self._prepare_work(stream_id, job, products)
        if not work_items:
            return False

        task = asyncio.create_task(
            self._run_background_job(
                stream_id,
                job.session_id,
                job.turn_id,
                work_items,
            )
        )
        with self._lock:
            current = self._jobs.get(stream_id)
            if current:
                current.task = task
        return True

    def mark_answer_complete(self, stream_id: str) -> None:
        should_finalize = False
        with self._lock:
            job = self._jobs.get(stream_id)
            if not job:
                return
            job.answer_complete = True
            should_finalize = (
                not job.finalized
                and (job.task is None or job.task.done())
            )
        if should_finalize:
            self._finalize_stream(stream_id)

    def _prepare_work(
        self,
        stream_id: str,
        job: _SidebarJob,
        products: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        work_items: list[dict[str, Any]] = []

        for product in products:
            ref = str(product.get("product_ref") or "").strip()
            if not ref:
                continue

            ids = _extract_ids(product, ref)
            patch: dict[str, Any] = {}
            fetch_sellers = False
            fetch_reviews = False

            if not product.get("seller_summary"):
                cached_sellers = cache_store.get_segment(ref, "sellers_snapshot") or {}
                if (
                    cache_store.is_fresh(ref, "sellers_snapshot")
                    and isinstance(cached_sellers, dict)
                    and cached_sellers.get("items")
                ):
                    patch["seller_summary"] = cached_sellers["items"]
                    patch["seller_summary_status"] = "ready"
                elif ids.get("product_id") or ids.get("gid"):
                    patch["seller_summary_status"] = "loading"
                    fetch_sellers = True
                else:
                    patch["seller_summary_status"] = "unavailable"

            if not product.get("review_summary"):
                cached_reviews = cache_store.get_segment(ref, "reviews_snapshot") or {}
                if (
                    cache_store.is_fresh(ref, "reviews_snapshot")
                    and isinstance(cached_reviews, dict)
                    and cached_reviews
                ):
                    patch["review_summary"] = cached_reviews
                    patch["review_summary_status"] = "ready"
                elif ids.get("gid"):
                    patch["review_summary_status"] = "loading"
                    fetch_reviews = True
                else:
                    patch["review_summary_status"] = "unavailable"

            if patch:
                stream_service.emit_product_patch(
                    stream_id,
                    job.session_id,
                    job.turn_id,
                    ref,
                    patch,
                    source_stage="sidebar_enrichment",
                )

            if fetch_sellers or fetch_reviews:
                work_items.append(
                    {
                        "ref": ref,
                        "ids": ids,
                        "fetch_sellers": fetch_sellers,
                        "fetch_reviews": fetch_reviews,
                    }
                )

        return work_items

    async def _run_background_job(
        self,
        stream_id: str,
        session_id: str,
        turn_id: str,
        work_items: list[dict[str, Any]],
    ) -> None:
        settings = get_settings()
        timeout = settings.agent.sidebar_enrichment_timeout_seconds
        semaphore = asyncio.Semaphore(settings.agent.max_concurrent_fetches)

        async def _fetch_sellers(ref: str, ids: dict[str, str]) -> tuple[str, str, Any]:
            async with semaphore:
                try:
                    return ref, "sellers", await dataforseo_gateway.get_sellers(ids)
                except Exception as exc:  # pragma: no cover - network path
                    log.warning("Background sellers fetch failed for %s: %s", ref, exc)
                    return ref, "sellers", None

        async def _fetch_reviews(ref: str, ids: dict[str, str]) -> tuple[str, str, Any]:
            async with semaphore:
                try:
                    return ref, "reviews", await dataforseo_gateway.get_reviews(ids["gid"])
                except Exception as exc:  # pragma: no cover - network path
                    log.warning("Background reviews fetch failed for %s: %s", ref, exc)
                    return ref, "reviews", None

        task_map: dict[asyncio.Task, tuple[str, str]] = {}
        for item in work_items:
            ref = item["ref"]
            ids = item["ids"]
            if item["fetch_sellers"]:
                task = asyncio.create_task(_fetch_sellers(ref, ids))
                task_map[task] = (ref, "sellers")
            if item["fetch_reviews"]:
                task = asyncio.create_task(_fetch_reviews(ref, ids))
                task_map[task] = (ref, "reviews")

        patches_by_ref: dict[str, dict[str, Any]] = {}
        try:
            done, pending = await asyncio.wait(task_map.keys(), timeout=timeout)
            if pending:
                log.warning(
                    "  [sidebar_enrichment] timed out after %ss; completed=%d pending=%d stream=%s",
                    timeout,
                    len(done),
                    len(pending),
                    stream_id,
                )
                for task in pending:
                    task.cancel()
                    ref, endpoint = task_map[task]
                    patch = patches_by_ref.setdefault(ref, {})
                    patch[_status_key(endpoint)] = "timeout"
                await asyncio.gather(*pending, return_exceptions=True)

            for task in done:
                if task.cancelled():
                    continue
                ref, endpoint, data = task.result()
                patch = patches_by_ref.setdefault(ref, {})
                if endpoint == "sellers":
                    if data:
                        cache_store.update_segment(
                            ref,
                            "sellers_snapshot",
                            {"items": data},
                            freshness_key="sellers_at",
                        )
                        patch["seller_summary"] = data
                        patch["seller_summary_status"] = "ready"
                    else:
                        patch.setdefault("seller_summary_status", "unavailable")
                elif endpoint == "reviews":
                    if data:
                        cache_store.update_segment(
                            ref,
                            "reviews_snapshot",
                            data,
                            freshness_key="reviews_at",
                        )
                        patch["review_summary"] = data
                        patch["review_summary_status"] = "ready"
                    else:
                        patch.setdefault("review_summary_status", "unavailable")

            for ref, patch in patches_by_ref.items():
                stream_service.emit_product_patch(
                    stream_id,
                    session_id,
                    turn_id,
                    ref,
                    patch,
                    source_stage="sidebar_enrichment",
                )
        except asyncio.CancelledError:
            for task in task_map:
                if not task.done():
                    task.cancel()
            await asyncio.gather(*task_map.keys(), return_exceptions=True)
            log.info("  [sidebar_enrichment] cancelled for stream=%s", stream_id)
            raise
        finally:
            with self._lock:
                job = self._jobs.get(stream_id)
                if job:
                    job.task = None
            self._maybe_finalize_after_background(stream_id)

    def _maybe_finalize_after_background(self, stream_id: str) -> None:
        should_finalize = False
        with self._lock:
            job = self._jobs.get(stream_id)
            if job:
                should_finalize = job.answer_complete and not job.finalized
        if should_finalize:
            self._finalize_stream(stream_id)

    def _finalize_stream(self, stream_id: str) -> None:
        session_id = ""
        turn_id = ""
        with self._lock:
            job = self._jobs.get(stream_id)
            if not job or job.finalized:
                return
            job.finalized = True
            session_id = job.session_id
            turn_id = job.turn_id

        stream_service.emit_stream_done(stream_id, session_id, turn_id)


def _status_key(endpoint: str) -> str:
    return "seller_summary_status" if endpoint == "sellers" else "review_summary_status"


def _extract_ids(product: dict[str, Any], ref: str) -> dict[str, str]:
    ids: dict[str, str] = {}
    if product.get("product_id"):
        ids["product_id"] = str(product["product_id"])
    elif "pid:" in ref:
        ids["product_id"] = ref.split("pid:")[-1]
    if product.get("gid"):
        ids["gid"] = str(product["gid"])
    if product.get("data_docid"):
        ids["data_docid"] = str(product["data_docid"])
    return ids


sidebar_enrichment_service = SidebarEnrichmentService()
