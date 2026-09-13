"""Pytest fixtures — isolate a temp DB and ensure the synthetic dataset exists."""
import os
import sys
from pathlib import Path

# Use a separate test database (set BEFORE importing the app).
os.environ["DATABASE_URL"] = "sqlite:///data/test_screening.db"

BACKEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND))

import pytest  # noqa: E402
from app.config import settings  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _prepare():
    # Fresh test DB.
    db_file = settings.data_dir / "test_screening.db"
    for suffix in ("", "-wal", "-shm"):
        f = Path(str(db_file) + suffix)
        if f.exists():
            f.unlink()
    from app.database import init_db
    init_db()

    # Ensure the synthetic dataset is present (generate if missing).
    if not (settings.synthetic_dir / "manifest.json").exists():
        import generate_synthetic_docs
        generate_synthetic_docs.main()
    yield


@pytest.fixture()
def db():
    from app.database import session_scope
    with session_scope() as s:
        yield s


def dataset_file(name_contains: str, genuine: bool) -> Path:
    import json
    manifest = json.loads((settings.synthetic_dir / "manifest.json").read_text())
    for d in manifest["documents"]:
        gt = d["ground_truth"] == ("GENUINE" if genuine else "ALTERED")
        if gt and name_contains in d["file"]:
            return settings.synthetic_dir / d["file"]
    raise FileNotFoundError(name_contains)
