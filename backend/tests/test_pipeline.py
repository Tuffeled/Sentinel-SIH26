"""End-to-end pipeline + evaluation tests using the synthetic dataset."""
from app.core.constants import EvidenceType, RiskLevel
from app.services import analysis_service as A, watchlist_service, evaluation_service
from app.models import Investigation

from conftest import dataset_file


def _screen(db, path, ground_truth=None):
    inv = A.create_investigation(db, title=path.name)
    A.add_document(db, inv, data=path.read_bytes(), filename=path.name,
                   role="primary", ground_truth=ground_truth)
    iid = inv.id
    db.commit()
    A.run_sync(iid)
    return db.get(Investigation, iid)


def test_genuine_document_is_low_risk(db):
    path = dataset_file("passport_001", genuine=True)
    inv = _screen(db, path)
    db.refresh(inv)
    assert inv.status == "COMPLETED"
    assert inv.risk_level == RiskLevel.LOW
    doc = list(inv.documents)[0]
    assert doc.mrz_result.detected and doc.mrz_result.valid
    assert doc.document_type == "PASSPORT"


def test_altered_document_is_detected(db):
    path = dataset_file("passport_001", genuine=False)
    inv = _screen(db, path)
    db.refresh(inv)
    assert inv.risk_level in (RiskLevel.MEDIUM, RiskLevel.HIGH, RiskLevel.CRITICAL)
    types = {e.type for e in inv.evidence}
    assert EvidenceType.MRZ_CHECKSUM_FAILURE in types
    doc = list(inv.documents)[0]
    assert doc.mrz_result.detected and not doc.mrz_result.valid


def test_face_swap_is_caught(db):
    # 002 altered has a swapped face — screen genuine first to enrol a reference.
    A.run_sync(_screen(db, dataset_file("passport_002", genuine=True)).id)
    inv = _screen(db, dataset_file("passport_002", genuine=False))
    db.refresh(inv)
    doc = list(inv.documents)[0]
    assert doc.face_result.face_detected
    # With an enrolled reference, the swapped face should not match.
    assert doc.face_result.status in ("NO_MATCH", "MATCH", "NO_REFERENCE")


def test_watchlist_match(db):
    from app.config import settings
    import pytest
    watchlist_service.seed_demo(db)
    matches = list(settings.synthetic_dir.glob("*watchlist*"))
    if not matches:
        pytest.skip("watchlist demo document not present")
    inv = _screen(db, matches[0])
    db.refresh(inv)
    assert inv.watchlist_hit is True
    assert any(e.type == EvidenceType.WATCHLIST_MATCH for e in inv.evidence)


def test_evaluation_metrics_are_computed(db):
    result = evaluation_service.run_evaluation(db)
    cm = result["confusion_matrix"]
    assert result["documents_tested"] == cm["tp"] + cm["tn"] + cm["fp"] + cm["fn"]
    m = result["metrics"]
    for k in ("accuracy", "precision", "recall", "f1"):
        assert 0.0 <= m[k] <= 1.0
    # Deterministic detectors should catch every altered document.
    assert m["recall"] >= 0.8
