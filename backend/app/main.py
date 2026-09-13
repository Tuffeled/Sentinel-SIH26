"""SENTINEL — AI-Based Fake Identity & Document Screening System (SIH26188).

FastAPI application: mounts all REST routers under /api, serves the vanilla-JS
frontend as static files, and initialises the SQLite database on startup.
"""
from __future__ import annotations

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from .config import settings
from .database import init_db
from .api import (
    analysis,
    cases,
    compare,
    dashboard,
    documents,
    evaluation,
    health,
    investigations,
    media,
    notifications,
    reports,
    reviews,
    search,
    settings_api,
    watchlist,
)

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))


@asynccontextmanager
async def lifespan(_app: FastAPI):
    settings.ensure_dirs()
    init_db()
    logging.getLogger("sentinel").info("Database initialised at %s", settings.database_url)
    yield


app = FastAPI(
    lifespan=lifespan,
    title="SENTINEL — Document Screening System",
    description=(
        "AI-assisted identity & document screening workstation (SIH26188). "
        "AI combines document, forensic, biometric, watchlist and consistency "
        "signals into an explainable risk assessment — the officer decides. "
        "DEMO MODE: synthetic documents only."
    ),
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# --- API routers ---
_API = "/api"
for module in (health, documents, analysis, investigations, compare, reviews,
               watchlist, dashboard, evaluation, reports, notifications, cases,
               search, settings_api, media):
    app.include_router(module.router, prefix=_API)


@app.get("/api")
def api_root() -> dict:
    return {
        "name": settings.app_name,
        "demo_mode": settings.demo_mode,
        "docs": "/docs",
        "message": "SENTINEL API — synthetic documents only.",
    }


@app.exception_handler(Exception)
async def _unhandled(request, exc):  # noqa: ANN001
    logging.getLogger("sentinel").exception("Unhandled error: %s", exc)
    return JSONResponse(status_code=500, content={"detail": "Internal server error"})


# --- Frontend static files (mounted last so /api wins) ---
if settings.frontend_dir.exists():
    app.mount("/", StaticFiles(directory=str(settings.frontend_dir), html=True), name="frontend")
