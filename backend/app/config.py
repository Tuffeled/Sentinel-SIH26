"""
Central configuration for the SIH26188 screening backend.

A tiny dependency-free .env loader is used so the app runs even if
``pydantic-settings`` is not installed. Relative paths in the configuration are
resolved against the project root (the folder that contains ``backend/`` and
``frontend/``).
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path


# backend/app/config.py -> parents[2] == project root
PROJECT_ROOT = Path(__file__).resolve().parents[2]


def _load_dotenv(path: Path) -> None:
    """Minimal .env parser (KEY=VALUE per line). Does not overwrite real env."""
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


_load_dotenv(PROJECT_ROOT / ".env")


def _get(key: str, default: str = "") -> str:
    return os.environ.get(key, default)


def _get_bool(key: str, default: bool) -> bool:
    return _get(key, str(default)).lower() in {"1", "true", "yes", "on"}


def _get_int(key: str, default: int) -> int:
    try:
        return int(_get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _get_float(key: str, default: float) -> float:
    try:
        return float(_get(key, str(default)))
    except (TypeError, ValueError):
        return default


def _autodetect_tesseract() -> str:
    """Locate the Tesseract binary when TESSERACT_CMD is not set."""
    import shutil

    found = shutil.which("tesseract")
    if found:
        return found
    for candidate in (
        r"C:\Program Files\Tesseract-OCR\tesseract.exe",
        r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
        os.path.expandvars(r"%LOCALAPPDATA%\Programs\Tesseract-OCR\tesseract.exe"),
        "/usr/bin/tesseract",
        "/usr/local/bin/tesseract",
        "/opt/homebrew/bin/tesseract",
    ):
        if candidate and os.path.exists(candidate):
            return candidate
    return ""


class Settings:
    """Runtime settings singleton."""

    def __init__(self) -> None:
        self.app_name: str = _get("APP_NAME", "SENTINEL Document Screening")
        self.demo_mode: bool = _get_bool("DEMO_MODE", True)
        self.officer_name: str = _get("OFFICER_NAME", "Officer")
        self.log_level: str = _get("LOG_LEVEL", "INFO")

        self.host: str = _get("HOST", "127.0.0.1")
        self.port: int = _get_int("PORT", 8000)

        # --- Paths ---
        self.project_root: Path = PROJECT_ROOT
        self.data_dir: Path = PROJECT_ROOT / "data"
        self.synthetic_dir: Path = self.data_dir / "synthetic"
        self.uploads_dir: Path = self.data_dir / "uploads"
        self.processed_dir: Path = self.data_dir / "processed"
        self.reports_dir: Path = self.data_dir / "reports"
        self.frontend_dir: Path = PROJECT_ROOT / "frontend"

        # Face-recognition model store (OpenCV YuNet detector + SFace embedder).
        self.app_dir: Path = Path(__file__).resolve().parent
        self.models_dir: Path = self.app_dir / "models_store"
        self.yunet_path: Path = self.models_dir / "yunet.onnx"
        self.sface_path: Path = self.models_dir / "sface.onnx"
        self.gan_faces_dir: Path = self.models_dir / "faces"

        db_url = _get("DATABASE_URL", "sqlite:///data/screening.db")
        # Resolve relative sqlite paths against the project root.
        if db_url.startswith("sqlite:///") and not db_url.startswith("sqlite:////"):
            rel = db_url.replace("sqlite:///", "", 1)
            abs_path = (PROJECT_ROOT / rel).resolve()
            db_url = f"sqlite:///{abs_path.as_posix()}"
        self.database_url: str = db_url

        # --- OCR ---
        self.tesseract_cmd: str = _get("TESSERACT_CMD", "") or _autodetect_tesseract()
        self.ocr_engine: str = _get("OCR_ENGINE", "auto").lower()

        # --- Face ---
        self.face_engine: str = _get("FACE_ENGINE", "auto").lower()
        # SFace cosine decision threshold (>= => same person).
        self.face_match_threshold: float = _get_float("FACE_MATCH_THRESHOLD", 0.363)

        # --- Uploads ---
        self.max_upload_mb: int = _get_int("MAX_UPLOAD_MB", 15)
        self.allowed_extensions: set[str] = {
            e.strip().lower().lstrip(".")
            for e in _get("ALLOWED_EXTENSIONS", "png,jpg,jpeg,pdf").split(",")
            if e.strip()
        }

        # --- Risk weights (points contributed per evidence type) ---
        self.risk_weights: dict[str, int] = {
            "MRZ_CHECKSUM_FAILURE": _get_int("RISK_WEIGHT_MRZ_CHECKSUM_FAILURE", 25),
            "FIELD_MISMATCH": _get_int("RISK_WEIGHT_FIELD_MISMATCH", 20),
            "FORENSIC_ANOMALY": _get_int("RISK_WEIGHT_FORENSIC_ANOMALY", 20),
            "FACE_LOW_SIMILARITY": _get_int("RISK_WEIGHT_FACE_LOW_SIMILARITY", 20),
            "WATCHLIST_MATCH": _get_int("RISK_WEIGHT_WATCHLIST_MATCH", 30),
            "CROSS_DOCUMENT_CONFLICT": _get_int("RISK_WEIGHT_CROSS_DOCUMENT_CONFLICT", 15),
            "OCR_LOW_CONFIDENCE": _get_int("RISK_WEIGHT_OCR_LOW_CONFIDENCE", 5),
            "METADATA_ANOMALY": _get_int("RISK_WEIGHT_METADATA_ANOMALY", 5),
            "CLASSIFICATION_UNCERTAIN": _get_int("RISK_WEIGHT_CLASSIFICATION_UNCERTAIN", 5),
        }

    def ensure_dirs(self) -> None:
        for d in (
            self.data_dir,
            self.synthetic_dir,
            self.uploads_dir,
            self.processed_dir,
            self.reports_dir,
        ):
            d.mkdir(parents=True, exist_ok=True)

    def as_public_dict(self) -> dict:
        """Non-sensitive settings safe to expose to the frontend."""
        return {
            "app_name": self.app_name,
            "demo_mode": self.demo_mode,
            "officer_name": self.officer_name,
            "ocr_engine": self.ocr_engine,
            "face_engine": self.face_engine,
            "face_match_threshold": self.face_match_threshold,
            "max_upload_mb": self.max_upload_mb,
            "allowed_extensions": sorted(self.allowed_extensions),
            "risk_weights": self.risk_weights,
        }


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
