"""Dataset evaluation endpoints."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..services import audit_service, evaluation_service

router = APIRouter(prefix="/evaluation", tags=["evaluation"])


@router.post("/run")
def run_evaluation(db: Session = Depends(get_db)) -> dict:
    result = evaluation_service.run_evaluation(db)
    audit_service.log(db, "EVALUATION_RUN",
                      details={"id": result["id"], "documents": result["documents_tested"]})
    return result


@router.get("/latest")
def latest() -> dict:
    result = evaluation_service.latest_run()
    if not result:
        return {"available": False,
                "message": "No evaluation has been run yet. POST /api/evaluation/run to start."}
    return {"available": True, **result}


@router.get("/dataset")
def dataset() -> dict:
    items = evaluation_service.load_dataset()
    return {
        "count": len(items),
        "genuine": sum(1 for i in items if i["ground_truth"] == "GENUINE"),
        "altered": sum(1 for i in items if i["ground_truth"] == "ALTERED"),
        "documents": [{"file": i["file"], "ground_truth": i["ground_truth"],
                       "identity": i.get("identity"), "type": i.get("type")} for i in items],
    }


@router.get("/{run_id}")
def get_run(run_id: str) -> dict:
    result = evaluation_service.get_run(run_id)
    if not result:
        raise HTTPException(status_code=404, detail="Evaluation run not found")
    return result
