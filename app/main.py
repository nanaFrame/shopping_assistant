"""FastAPI application entry point."""

from __future__ import annotations

import logging
import logging.handlers
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import get_settings
from app.api.routes import health, sessions, chat, stream

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

# Static test page
_TEST_PAGE_DIR = Path(__file__).parent / "web" / "test_page"
app.mount("/static", StaticFiles(directory=str(_TEST_PAGE_DIR)), name="static")


@app.get("/")
async def index():
    return FileResponse(str(_TEST_PAGE_DIR / "index.html"))
