"""FastAPI application entry point."""

from __future__ import annotations

import json
import logging
import logging.handlers
from pathlib import Path
from urllib.parse import urlparse

import httpx
from fastapi import FastAPI
from fastapi import HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.responses import HTMLResponse
from fastapi.responses import Response
from fastapi.staticfiles import StaticFiles

from app.application.suggestion_pool import SUGGESTION_POOL
from app.config import get_settings
from app.api.routes import health, sessions, chat, stream, suggestions

_LOG_DIR = Path(__file__).resolve().parent.parent / "data" / "logs"
_LOG_DIR.mkdir(parents=True, exist_ok=True)

_log_formatter = logging.Formatter(
    "%(asctime)s %(levelname)-8s [%(name)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_log_formatter)

_file_handler = logging.handlers.RotatingFileHandler(
    _LOG_DIR / "app.log",
    maxBytes=10 * 1024 * 1024,
    backupCount=5,
    encoding="utf-8",
)
_file_handler.setFormatter(_log_formatter)

logging.basicConfig(
    level=logging.INFO,
    handlers=[_console_handler, _file_handler],
)

settings = get_settings()
log = logging.getLogger(__name__)

app = FastAPI(title="Shopping Assistant", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.server.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Routes
app.include_router(health.router)
app.include_router(sessions.router)
app.include_router(chat.router)
app.include_router(stream.router)
app.include_router(suggestions.router)

# Static test page
_TEST_PAGE_DIR = Path(__file__).parent / "web" / "test_page"
app.mount("/static", StaticFiles(directory=str(_TEST_PAGE_DIR)), name="static")


@app.get("/")
async def index():
    html = (_TEST_PAGE_DIR / "index.html").read_text(encoding="utf-8")
    return HTMLResponse(
        html.replace(
            "__SUGGESTION_POOL__",
            json.dumps(SUGGESTION_POOL, ensure_ascii=False),
        )
    )


@app.get("/api/image")
async def proxy_image(url: str):
    """Proxy external product images to avoid hotlink/referrer blocking."""
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise HTTPException(status_code=400, detail="Invalid image URL")

    try:
        async with httpx.AsyncClient(follow_redirects=True, timeout=20.0) as client:
            resp = await client.get(
                url,
                headers={
                    "User-Agent": "Mozilla/5.0 ShoppingAssistant/1.0",
                    "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
                    "Referer": "",
                },
            )
            resp.raise_for_status()
    except httpx.HTTPError as exc:
        log.warning("Image proxy failed for %s: %s", url, exc)
        raise HTTPException(status_code=502, detail="Failed to fetch image") from exc

    media_type = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
    return Response(
        content=resp.content,
        media_type=media_type,
        headers={"Cache-Control": "public, max-age=86400"},
    )
