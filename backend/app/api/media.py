"""Serve processed forensic / face images (never from a public static dir)."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

from ..config import settings

router = APIRouter(tags=["media"])


@router.get("/media/processed/{name}")
def processed_media(name: str):
    # Only basenames from the processed dir are allowed.
    candidate = (settings.processed_dir / Path(name).name).resolve()
    if settings.processed_dir.resolve() not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(candidate)


@router.get("/media/reports/{name}")
def report_media(name: str):
    candidate = (settings.reports_dir / Path(name).name).resolve()
    if settings.reports_dir.resolve() not in candidate.parents:
        raise HTTPException(status_code=400, detail="Invalid path")
    if not candidate.exists():
        raise HTTPException(status_code=404, detail="Not found")
    return FileResponse(candidate, media_type="application/pdf", filename=Path(name).name)
