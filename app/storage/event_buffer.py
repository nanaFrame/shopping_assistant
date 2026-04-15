"""In-memory event buffer — stores streaming events per stream_id.

Supports append, replay from seq, draining new events, and stream completion.
"""

from __future__ import annotations

import threading
from typing import Any


class EventBuffer:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        # stream_id -> {"meta": {...}, "events": [...], "done": bool}
        self._streams: dict[str, dict[str, Any]] = {}

    def create_stream(
        self, stream_id: str, session_id: str, turn_id: str
    ) -> None:
        with self._lock:
            self._streams[stream_id] = {
                "meta": {
                    "session_id": session_id,
                    "turn_id": turn_id,
                    "stream_id": stream_id,
                },
                "events": [],
                "done": False,
            }

    def get_stream_meta(self, stream_id: str) -> dict[str, Any] | None:
        entry = self._streams.get(stream_id)
        return entry["meta"] if entry else None

    def next_seq(self, stream_id: str) -> int:
        entry = self._streams.get(stream_id)
        if entry is None:
            return 1
        return len(entry["events"]) + 1

    def append(self, stream_id: str, event: dict[str, Any]) -> None:
        with self._lock:
            entry = self._streams.get(stream_id)
            if entry is None:
                return
            entry["events"].append(event)

    def replay(
        self, stream_id: str, after_seq: int = 0
    ) -> list[dict[str, Any]]:
        entry = self._streams.get(stream_id)
        if entry is None:
            return []
        return [e for e in entry["events"] if e.get("seq", 0) > after_seq]

    def drain_new(
        self, stream_id: str, after_seq: int = 0
    ) -> list[dict[str, Any]]:
        """Return events with seq > after_seq (non-destructive)."""
        return self.replay(stream_id, after_seq)

    def is_stream_done(self, stream_id: str) -> bool:
        entry = self._streams.get(stream_id)
        return entry["done"] if entry else True

    def mark_done(self, stream_id: str) -> None:
        with self._lock:
            entry = self._streams.get(stream_id)
            if entry:
                entry["done"] = True


event_buffer = EventBuffer()
