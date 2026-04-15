"""SQLite-backed product cache with per-segment TTL."""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings

log = logging.getLogger(__name__)

_DDL = """
CREATE TABLE IF NOT EXISTS product_cache (
    product_ref   TEXT PRIMARY KEY,
    data_json     TEXT NOT NULL,
    updated_at    TEXT NOT NULL
);
"""

_EMPTY_ENTRY_TEMPLATE = {
    "product_ref": "",
    "identifiers": {},
    "base_card": {},
    "product_info_snapshot": {},
    "sellers_snapshot": {},
    "reviews_snapshot": {},
    "freshness": {},
}


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


class CacheStore:
    def __init__(self) -> None:
        self._db_path: str | None = None
        self._conn: sqlite3.Connection | None = None

    def _ensure_db(self) -> sqlite3.Connection:
        if self._conn is not None:
            return self._conn
        cfg = get_settings()
        self._db_path = cfg.cache.sqlite_path
        Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(self._db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(_DDL)
        self._conn.commit()
        self._migrate_json_files(cfg.cache.json_legacy_path)
        return self._conn

    def _migrate_json_files(self, legacy_path: str) -> None:
        """One-time migration: import existing JSON cache files into SQLite."""
        legacy_dir = Path(legacy_path)
        if not legacy_dir.exists():
            return
        json_files = list(legacy_dir.glob("*.json"))
        if not json_files:
            return
        log.info("[CacheStore] Migrating %d JSON cache files to SQLite...", len(json_files))
        conn = self._conn
        assert conn is not None
        migrated = 0
        for fp in json_files:
            try:
                with open(fp, encoding="utf-8") as f:
                    data = json.load(f)
                ref = data.get("product_ref", "")
                if not ref:
                    continue
                row = conn.execute(
                    "SELECT 1 FROM product_cache WHERE product_ref = ?", (ref,)
                ).fetchone()
                if row:
                    continue
                conn.execute(
                    "INSERT INTO product_cache (product_ref, data_json, updated_at) VALUES (?, ?, ?)",
                    (ref, json.dumps(data, ensure_ascii=False), _now()),
                )
                migrated += 1
            except Exception as e:
                log.warning("[CacheStore] Failed to migrate %s: %s", fp.name, e)
        if migrated:
            conn.commit()
            log.info("[CacheStore] Migrated %d/%d JSON files into SQLite", migrated, len(json_files))
            for fp in json_files:
                try:
                    fp.unlink()
                except OSError:
                    pass
            try:
                if not any(legacy_dir.iterdir()):
                    legacy_dir.rmdir()
            except OSError:
                pass
            log.info("[CacheStore] Cleaned up legacy JSON cache files")

    # ── Read / Write ──────────────────────────────────────────

    def get(self, product_ref: str) -> dict[str, Any] | None:
        conn = self._ensure_db()
        row = conn.execute(
            "SELECT data_json FROM product_cache WHERE product_ref = ?",
            (product_ref,),
        ).fetchone()
        if row is None:
            return None
        return json.loads(row[0])

    def save(self, product_ref: str, data: dict[str, Any]) -> None:
        conn = self._ensure_db()
        conn.execute(
            "INSERT OR REPLACE INTO product_cache (product_ref, data_json, updated_at) VALUES (?, ?, ?)",
            (product_ref, json.dumps(data, ensure_ascii=False), _now()),
        )
        conn.commit()

    # ── Segment helpers ───────────────────────────────────────

    def get_segment(
        self, product_ref: str, segment: str
    ) -> dict[str, Any] | None:
        entry = self.get(product_ref)
        if entry is None:
            return None
        return entry.get(segment)

    def update_segment(
        self,
        product_ref: str,
        segment: str,
        data: dict[str, Any],
        *,
        freshness_key: str | None = None,
    ) -> None:
        entry = self.get(product_ref) or {
            **_EMPTY_ENTRY_TEMPLATE,
            "product_ref": product_ref,
        }
        entry[segment] = data
        if freshness_key:
            entry.setdefault("freshness", {})[freshness_key] = _now()
        self.save(product_ref, entry)

    def update_identifiers(
        self, product_ref: str, identifiers: dict[str, Any]
    ) -> None:
        entry = self.get(product_ref) or {
            **_EMPTY_ENTRY_TEMPLATE,
            "product_ref": product_ref,
        }
        entry.setdefault("identifiers", {}).update(identifiers)
        self.save(product_ref, entry)

    # ── Freshness ─────────────────────────────────────────────

    def is_fresh(self, product_ref: str, segment: str) -> bool:
        entry = self.get(product_ref)
        if entry is None:
            return False
        freshness = entry.get("freshness", {})
        key_map = {
            "base_card": "base_card_at",
            "product_info_snapshot": "product_info_at",
            "sellers_snapshot": "sellers_at",
            "reviews_snapshot": "reviews_at",
        }
        ts_key = key_map.get(segment)
        if not ts_key:
            return False
        ts_str = freshness.get(ts_key)
        if not ts_str:
            return False
        ts = datetime.fromisoformat(ts_str)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        ttl = self._ttl_for(segment)
        return datetime.now(timezone.utc) - ts < ttl

    def _ttl_for(self, segment: str) -> timedelta:
        cfg = get_settings().cache.ttl
        ttl_map = {
            "base_card": timedelta(hours=cfg.base_card_hours),
            "product_info_snapshot": timedelta(days=cfg.product_info_days),
            "sellers_snapshot": timedelta(hours=cfg.sellers_hours),
            "reviews_snapshot": timedelta(days=cfg.reviews_days),
        }
        return ttl_map.get(segment, timedelta(hours=24))

    def invalidate(self, product_ref: str) -> None:
        conn = self._ensure_db()
        conn.execute(
            "DELETE FROM product_cache WHERE product_ref = ?", (product_ref,)
        )
        conn.commit()

    def count(self) -> int:
        """Return total number of cached products."""
        conn = self._ensure_db()
        row = conn.execute("SELECT COUNT(*) FROM product_cache").fetchone()
        return row[0] if row else 0


cache_store = CacheStore()
