"""Secure file-handling helpers.

* validates extension / size / magic bytes
* generates server-side filenames (never trusts the uploaded name)
* prevents path traversal
"""
from __future__ import annotations

import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from ..config import settings

# Magic-byte signatures for the formats we accept.
_MAGIC = {
    b"\x89PNG\r\n\x1a\n": "png",
    b"\xff\xd8\xff": "jpg",
    b"%PDF": "pdf",
}


class FileValidationError(Exception):
    """Raised when an uploaded file fails validation."""


def detect_kind(data: bytes) -> str | None:
    """Return a canonical file kind from magic bytes, or None if unknown."""
    for sig, kind in _MAGIC.items():
        if data.startswith(sig):
            return kind
    return None


def validate_upload(filename: str, data: bytes) -> str:
    """Validate an uploaded file. Returns the canonical extension.

    Raises FileValidationError on any problem.
    """
    if not data:
        raise FileValidationError("Uploaded file is empty.")

    size_mb = len(data) / (1024 * 1024)
    if size_mb > settings.max_upload_mb:
        raise FileValidationError(
            f"File too large ({size_mb:.1f} MB). Maximum is {settings.max_upload_mb} MB."
        )

    ext = (Path(filename).suffix or "").lower().lstrip(".")
    if ext == "jpeg":
        ext = "jpg"
    if ext not in settings.allowed_extensions and not (
        ext == "jpg" and "jpeg" in settings.allowed_extensions
    ):
        raise FileValidationError(
            f"Unsupported file type '.{ext}'. Allowed: "
            f"{', '.join(sorted(settings.allowed_extensions))}."
        )

    kind = detect_kind(data)
    if kind is None:
        raise FileValidationError(
            "File content does not match a supported PNG/JPG/PDF signature."
        )

    # Extension and content must agree (jpg/jpeg treated the same).
    norm_ext = "jpg" if ext == "jpeg" else ext
    if kind != norm_ext:
        raise FileValidationError(
            f"File content ({kind}) does not match extension (.{ext})."
        )
    return kind


def safe_stored_name(kind: str) -> str:
    """Generate an unguessable, safe, server-side filename."""
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    token = secrets.token_hex(6)
    return f"doc_{stamp}_{token}.{kind}"


def new_uuid() -> str:
    return uuid.uuid4().hex


def resolve_within(base: Path, name: str) -> Path:
    """Resolve *name* strictly inside *base*, blocking path-traversal."""
    base = base.resolve()
    candidate = (base / Path(name).name).resolve()
    if base not in candidate.parents and candidate != base:
        raise FileValidationError("Path traversal detected.")
    return candidate
