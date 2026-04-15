from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Query, Request
from sse_starlette.sse import EventSourceResponse

from app.config import get_settings
from app.domain.events import ApiResponse
from app.storage.event_buffer import event_buffer

router = APIRouter()


@router.get("/api/stream")
async def stream(
    request: Request,
    session_id: str = Query(...),
    turn_id: str = Query(...),
    stream_id: str = Query(...),
    last_seq: int = Query(0),
    replay: bool = Query(True),
):
    meta = event_buffer.get_stream_meta(stream_id)
    if meta is None:
        return ApiResponse.fail("STREAM_NOT_FOUND", "stream does not exist").model_dump()
    if meta["session_id"] != session_id or meta["turn_id"] != turn_id:
        return ApiResponse.fail(
            "STREAM_BINDING_MISMATCH",
            "session_id/turn_id do not match stream_id",
        ).model_dump()

    settings = get_settings()
    heartbeat_sec = settings.stream.heartbeat_interval_seconds

    async def event_generator():
        sent_seq = last_seq

        # Replay buffered events
        if replay:
            for evt in event_buffer.replay(stream_id, after_seq=last_seq):
                if await request.is_disconnected():
                    return
                sent_seq = evt["seq"]
                yield {
                    "event": "message",
                    "id": evt["event_id"],
                    "data": json.dumps(evt, ensure_ascii=False),
                }

        # Live events — poll at 0.1s for token-level streaming responsiveness
        poll_interval = 0.1
        since_heartbeat = 0.0

        while not await request.is_disconnected():
            new_events = event_buffer.drain_new(stream_id, after_seq=sent_seq)
            if new_events:
                for evt in new_events:
                    sent_seq = evt["seq"]
                    yield {
                        "event": "message",
                        "id": evt["event_id"],
                        "data": json.dumps(evt, ensure_ascii=False),
                    }
                    if evt.get("type") in ("stream_done", "error"):
                        return
                since_heartbeat = 0.0
            else:
                if event_buffer.is_stream_done(stream_id):
                    return
                since_heartbeat += poll_interval
                if since_heartbeat >= heartbeat_sec:
                    yield {"event": "heartbeat", "data": ""}
                    since_heartbeat = 0.0
                await asyncio.sleep(poll_interval)

    return EventSourceResponse(event_generator())
