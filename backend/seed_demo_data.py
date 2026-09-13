"""CLI to seed / clear / reset the synthetic demonstration database.

Usage (from the backend/ directory, venv active):
    python seed_demo_data.py            # init DB + seed watchlist + run pipeline on dataset
    python seed_demo_data.py --reset    # wipe everything, reseed watchlist only
    python seed_demo_data.py --clear    # wipe screenings/cases (keep watchlist)
    python seed_demo_data.py --watchlist-only

All generated data is clearly synthetic. Seeding runs the REAL analysis pipeline
over the synthetic dataset, so dashboard figures come from genuine analysis.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from app.database import init_db, session_scope  # noqa: E402
from app.services import demo_service, watchlist_service  # noqa: E402
from app.services.evaluation_service import load_dataset  # noqa: E402


def main() -> None:
    ap = argparse.ArgumentParser(description="Seed the SENTINEL synthetic demo database.")
    ap.add_argument("--reset", action="store_true", help="Delete ALL data, reseed watchlist only.")
    ap.add_argument("--clear", action="store_true", help="Delete screenings/cases (keep watchlist).")
    ap.add_argument("--watchlist-only", action="store_true", help="Only seed the synthetic watchlist.")
    args = ap.parse_args()

    init_db()
    print("Database initialised.")

    if args.reset:
        with session_scope() as db:
            demo_service.reset_demo(db)
        print("Database reset; synthetic watchlist reseeded.")
        return
    if args.clear:
        with session_scope() as db:
            demo_service.clear_demo(db)
        print("Screening/case data cleared (watchlist kept).")
        return
    if args.watchlist_only:
        with session_scope() as db:
            n = watchlist_service.seed_demo(db)
        print(f"Seeded {n} synthetic watchlist records.")
        return

    dataset = load_dataset()
    if not dataset:
        print("WARNING: no synthetic dataset found in data/synthetic/.")
        print("  Generate it first:  python generate_synthetic_docs.py")
        with session_scope() as db:
            watchlist_service.seed_demo(db)
        print("Seeded synthetic watchlist only.")
        return

    print(f"Seeding demo data (running the real pipeline over {len(dataset)} synthetic documents)…")
    result = demo_service.seed_demo_standalone()
    print(f"Done. {result.get('screenings', 0)} screenings created; watchlist seeded.")
    print("Start the backend (run_backend.bat) and open http://127.0.0.1:8000/")


if __name__ == "__main__":
    main()
