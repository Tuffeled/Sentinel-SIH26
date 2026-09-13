"""Document upload, listing, retrieval and image serving."""
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..core.security import FileValidationError
from ..database import get_db
from ..models import Document, Investigation
from ..schemas import serializers as S
from ..services import analysis_service

router = APIRouter(prefix="/documents", tags=["documents"])


@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    investigation_id: int | None = Form(default=None),
    role: str = Form(default="primary"),
    auto_analyze: bool = Form(default=True),
    ground_truth: str | None = Form(default=None),
    title: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict:
    data = await file.read()
    try:
        # Create or reuse the investigation.
        if investigation_id:
            inv = db.get(Investigation, investigation_id)
            if not inv:
                raise HTTPException(status_code=404, detail="Investigation not found")
        else:
            inv = analysis_service.create_investigation(db, title=title)

        doc = analysis_service.add_document(
            db, inv, data=data, filename=file.filename or "upload",
            role=role, ground_truth=ground_truth)
    except FileValidationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    started = False
    if auto_analyze and role != "reference":
        analysis_service.start_analysis(inv.id)
        started = True

    db.refresh(inv)
    return {
        "investigation_id": inv.id,
        "screening_id": inv.screening_id,
        "document": S.document_summary(doc),
        "analysis_started": started,
    }


@router.get("")
def list_documents(limit: int = 100, offset: int = 0, db: Session = Depends(get_db)) -> dict:
    rows = db.execute(
        select(Document).order_by(Document.created_at.desc()).limit(limit).offset(offset)
    ).scalars().all()
    return {"documents": [S.document_summary(d) for d in rows]}


@router.get("/{document_id}")
def get_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    return S.document_full(doc)


@router.get("/{document_id}/image")
def document_image(document_id: int, db: Session = Depends(get_db)):
    doc = db.get(Document, document_id)
    if not doc:
        raise HTTPException(status_code=404, detail="Document not found")
    path = (settings.uploads_dir / Path(doc.stored_filename).name).resolve()
    if settings.uploads_dir.resolve() not in path.parents or not path.exists():
        raise HTTPException(status_code=404, detail="Image not found")
    media = "application/pdf" if doc.file_kind == "pdf" else f"image/{doc.file_kind}"
    return FileResponse(path, media_type=media)


@router.post("/{document_id}/analyze")
def analyze_document(document_id: int, db: Session = Depends(get_db)) -> dict:
    doc = db.get(Document, document_id)
    if not doc or not doc.investigation_id:
        raise HTTPException(status_code=404, detail="Document/investigation not found")
    inv = db.get(Investigation, doc.investigation_id)
    inv.stages = analysis_service._init_stages()
    inv.status = "QUEUED"
    db.add(inv)
    db.commit()
    analysis_service.start_analysis(inv.id)
    return {"investigation_id": inv.id, "screening_id": inv.screening_id, "analysis_started": True}
