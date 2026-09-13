"""Image loading / conversion helpers shared by the CV services."""
from __future__ import annotations

import hashlib
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from ..config import settings


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def is_pdf(path: str | Path) -> bool:
    return str(path).lower().endswith(".pdf")


def _pdf_first_page_to_array(path: Path) -> np.ndarray | None:
    """Render the first PDF page to a BGR array using PyMuPDF if available."""
    try:
        import fitz  # PyMuPDF (optional)
    except Exception:
        return None
    try:
        doc = fitz.open(str(path))
        page = doc.load_page(0)
        pix = page.get_pixmap(dpi=200)
        img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(pix.height, pix.width, pix.n)
        if pix.n == 4:
            img = cv2.cvtColor(img, cv2.COLOR_RGBA2BGR)
        elif pix.n == 3:
            img = cv2.cvtColor(img, cv2.COLOR_RGB2BGR)
        else:
            img = cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)
        return img
    except Exception:
        return None


def load_bgr(path: str | Path) -> np.ndarray:
    """Load an image (or first PDF page) as an OpenCV BGR array.

    Raises RuntimeError if the file cannot be decoded (e.g. PDF without a
    renderer installed) so the pipeline can degrade honestly.
    """
    path = Path(path)
    if is_pdf(path):
        arr = _pdf_first_page_to_array(path)
        if arr is None:
            raise RuntimeError(
                "PDF rasterisation unavailable (install PyMuPDF for PDF support)."
            )
        return arr
    # Use PIL first (handles more edge cases / EXIF) then convert.
    with Image.open(path) as im:
        im = im.convert("RGB")
        arr = np.array(im)[:, :, ::-1].copy()  # RGB -> BGR
    return arr


def load_pil(path: str | Path) -> Image.Image:
    path = Path(path)
    if is_pdf(path):
        arr = _pdf_first_page_to_array(path)
        if arr is None:
            raise RuntimeError("PDF rasterisation unavailable.")
        return Image.fromarray(arr[:, :, ::-1])
    return Image.open(path).convert("RGB")


def image_size(path: str | Path) -> tuple[int, int]:
    try:
        img = load_bgr(path)
        return int(img.shape[1]), int(img.shape[0])
    except Exception:
        return 0, 0


def to_relative(path: str | Path) -> str:
    """Return a path relative to the data dir (for API references), POSIX style."""
    p = Path(path).resolve()
    try:
        return p.relative_to(settings.data_dir.resolve()).as_posix()
    except ValueError:
        return p.name


def processed_path(name: str) -> Path:
    settings.processed_dir.mkdir(parents=True, exist_ok=True)
    return settings.processed_dir / name


def save_bgr(img: np.ndarray, name: str) -> Path:
    out = processed_path(name)
    cv2.imwrite(str(out), img)
    return out
