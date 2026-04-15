"""JSONL event log — persists streaming events to disk for debugging."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.config import get_settings


class EventLog:
    def __init__(self) -> None:
        self._base: Path | None = None

    def _ensure_dir(self) -> Path:
        if self._base is None:
            self._base = Path(get_settings().storage.event_log_path)
        self._base.mkdir(parents=True, exist_ok=True)
        return self._base

    def log_event(
        self,
        stream_id: str,
        event: dict[str, Any],
    ) -> None:
        d = self._ensure_dir()
        path = d / f"{stream_id}.jsonl"
        entry = {
            "logged_at": datetime.now(timezone.utc).isoformat(),
            **event,
        }
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(entry, ensure_ascii=False) + "\n")

    def read_events(self, stream_id: str) -> list[dict[str, Any]]:
        d = self._ensure_dir()
        path = d / f"{stream_id}.jsonl"
        if not path.exists():
            return []
        events = []
        with open(path, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line:
                    events.append(json.loads(line))
        return events


event_log = EventLog()
