"""Unit tests for the deterministic core (no DB required)."""
from app.services import mrz_service, validation_service, risk_service, evidence_service
from app.services.document_classifier import document_classifier
from app.core import security
from app.core.constants import EvidenceType, RiskLevel
from app.utils.text import normalize_doc_number, normalize_date


# ---------------- MRZ checksums ----------------
def test_check_digit_known_values():
    # ICAO 9303 worked examples.
    assert mrz_service.check_digit("L898902C3") == 6
    assert mrz_service.check_digit("740812") == 2
    assert mrz_service.check_digit("120415") == 9


def test_td3_parse_and_validate():
    lines = [
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
        "L898902C36UTO7408122F1204159ZE184226B<<<<<10",
    ]
    parsed = mrz_service.parse_td3(lines)
    assert parsed["fields"]["surname"] == "ERIKSSON"
    assert parsed["fields"]["document_number"] == "L898902C3"
    assert parsed["checks"]["document_number"] == "PASS"
    assert parsed["checks"]["date_of_birth"] == "PASS"
    assert parsed["checks"]["expiry_date"] == "PASS"


def test_td3_detects_corrupted_checksum():
    # Corrupt the document-number check digit (6 -> 5).
    lines = [
        "P<UTOERIKSSON<<ANNA<MARIA<<<<<<<<<<<<<<<<<<<",
        "L898902C35UTO7408122F1204159ZE184226B<<<<<10",
    ]
    parsed = mrz_service.parse_td3(lines)
    assert parsed["checks"]["document_number"] == "FAIL"


# ---------------- Field consistency ----------------
def test_field_consistency_match_and_mismatch():
    ocr = {"surname": "ERIKSSON", "dob": "1974-08-12", "document_number": "L898902C3"}
    mrz = {"surname": "ERIKSSON", "dob": "1974-08-12", "document_number": "L898902C3"}
    assert validation_service.check_consistency(ocr, mrz)["overall"] == "CONSISTENT"

    mrz2 = dict(mrz, dob="1980-08-12")
    res = validation_service.check_consistency(ocr, mrz2)
    assert res["overall"] == "MISMATCH"
    assert any(m["field"] == "dob" for m in res["mismatches"])


# ---------------- Risk engine ----------------
def test_risk_engine_deterministic_and_deduped():
    evidence = [
        {"type": EvidenceType.MRZ_CHECKSUM_FAILURE, "risk_contribution": 25, "severity": "HIGH", "confidence": 0.98},
        {"type": EvidenceType.FIELD_MISMATCH, "risk_contribution": 20, "severity": "HIGH", "confidence": 0.9},
        {"type": EvidenceType.FIELD_MISMATCH, "risk_contribution": 20, "severity": "MEDIUM", "confidence": 0.9},
    ]
    r = risk_service.calculate(evidence)
    # FIELD_MISMATCH counted once -> 25 + 20 = 45
    assert r["score"] == 45
    assert r["level"] == RiskLevel.MEDIUM
    # Same input -> same output (deterministic)
    assert risk_service.calculate(evidence)["score"] == 45


def test_risk_score_capped_at_100():
    evidence = [{"type": t, "risk_contribution": 30, "severity": "CRITICAL", "confidence": 1.0}
                for t in (EvidenceType.WATCHLIST_MATCH, EvidenceType.MRZ_CHECKSUM_FAILURE,
                          EvidenceType.FORENSIC_ANOMALY, EvidenceType.FACE_LOW_SIMILARITY)]
    assert risk_service.calculate(evidence)["score"] <= 100


# ---------------- Evidence generation ----------------
def test_evidence_from_watchlist_match():
    ctx = {"watchlist": {"match": True, "record": {"status": "STOLEN", "document_number": "X"}}}
    ev = evidence_service.from_watchlist(ctx["watchlist"])
    assert ev and ev[0]["type"] == EvidenceType.WATCHLIST_MATCH
    assert ev[0]["risk_contribution"] > 0


# ---------------- Classifier ----------------
def test_classifier_passport_from_mrz():
    mrz = {"detected": True, "mrz_type": "TD3", "fields": {"document_type": "P"}}
    out = document_classifier.classify("REPUBLIC PASSPORT", mrz)
    assert out["document_type"] == "PASSPORT"
    assert out["confidence"] > 0.5


# ---------------- Security / upload ----------------
def test_upload_validation_rejects_bad_content():
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 100
    assert security.validate_upload("x.png", png) == "png"
    try:
        security.validate_upload("x.png", b"not a png")
        assert False, "should have raised"
    except security.FileValidationError:
        pass


def test_normalizers():
    assert normalize_doc_number("P123 456 789") == "P123456789"
    assert normalize_date("12 APR 1990") == "1990-04-12"
