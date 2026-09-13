"""API endpoint tests via FastAPI TestClient."""
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health():
    r = client.get("/api/health")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] in ("operational", "busy")
    assert "ocr" in body and "face" in body


def test_watchlist_seed_and_list():
    assert client.post("/api/watchlist/seed-demo").status_code == 200
    r = client.get("/api/watchlist")
    assert r.status_code == 200
    data = r.json()
    assert data["stats"]["total"] >= 1
    assert "SYNTHETIC" in data["notice"]


def test_watchlist_search_no_match_message():
    r = client.get("/api/watchlist/search", params={"document_number": "ZZZ-NOPE-000"})
    assert r.status_code == 200
    assert r.json()["match"] is False
    assert "does NOT mean" in r.json()["note"]


def test_dashboard_stats_keys():
    r = client.get("/api/dashboard/stats")
    assert r.status_code == 200
    for k in ("documents_screened", "flagged_for_review", "high_risk_cases", "avg_screening_time_sec"):
        assert k in r.json()


def test_upload_rejects_bad_file():
    files = {"file": ("bad.png", b"not a real png", "image/png")}
    r = client.post("/api/documents/upload", files=files, data={"auto_analyze": "false"})
    assert r.status_code == 400


def test_openapi_available():
    r = client.get("/openapi.json")
    assert r.status_code == 200
    assert len(r.json()["paths"]) > 20
