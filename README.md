# SENTINEL — AI-Based Fake Identity & Document Screening System

**Smart India Hackathon · Problem Statement SIH26188**

> An evidence-driven identity and document screening **workstation** that combines
> multiple independent signals — document classification, OCR, MRZ validation,
> forensic analysis, face verification, watchlist lookup and cross-document
> consistency — into a single **explainable risk assessment**, and hands the final
> decision to an authorised human officer.

> ### ⚠ DEMO MODE — SYNTHETIC DOCUMENTS ONLY
> This system operates exclusively on **fictional, synthetic** identity documents
> generated for demonstration. It never connects to real government or
> stolen-document databases, and it never produces counterfeit real-world
> documents.

---

## 1. Problem Overview

Fraudulent and tampered identity documents are a serious risk at borders, in
banking (KYC), and in any identity-verification workflow. A naïve "AI fake
detector" that outputs a single *genuine/fake* verdict is both unreliable and
dangerous — it hides its reasoning and removes the human from the loop.

## 2. Solution Overview

SENTINEL is **not** a single classifier. It is a screening pipeline of independent
analysis modules, each producing **structured evidence**. A deterministic,
explainable **risk engine** combines that evidence into a 0–100 score, and an
**authorised officer** reviews the findings and makes the final decision.

```
DOCUMENT → MULTIPLE ANALYSIS MODULES → EVIDENCE → RISK ASSESSMENT
        → HUMAN OFFICER REVIEW → FINAL DECISION → CASE / AUDIT
```

**Core principle:** *AI does not replace the officer. It analyses documents,
identifies inconsistencies, checks the local synthetic watchlist, examines
forensic signals, compares identities across documents, and organises the
findings into an explainable risk assessment. The authorised officer remains
responsible for the final decision.*

## 3. Architecture

```
                    FRONTEND
              HTML / CSS / Vanilla JS
                        │  REST API (fetch)
                        ▼
                     FASTAPI
                        │
      ┌─────────────────┼─────────────────┐
     OCR               MRZ            FORENSICS
   (Tesseract)   (ICAO 9303 checks)  (ELA / noise /
      │                │              copy-move /
      └─────────────────┼──── reference-difference)
                        │
                 FACE VERIFICATION
              (OpenCV YuNet + SFace)
                        │
                 WATCHLIST LOOKUP
              (local synthetic SQLite)
                        │
              CROSS-DOCUMENT CHECK
                        │
                        ▼
                 EVIDENCE ENGINE  ──►  RISK ENGINE (deterministic)
                        │
                        ▼
                  HUMAN REVIEW
                        │
                        ▼
              CASE / AUDIT SYSTEM
                        │
                        ▼
                     SQLITE
```

## 4. Key Features & Differentiators

1. **Explainable, evidence-based risk assessment** — every point in the 0–100
   score traces to a specific evidence item; nothing is a black box.
2. **Human-in-the-loop** — officers accept or **override** the AI recommendation,
   with the override and justification recorded.
3. **Cross-document identity consistency** — link a passport + visa + ID and get a
   consistency matrix (name / DOB / nationality / face).
4. **Synthetic genuine-vs-altered evaluation** — real accuracy / precision /
   recall / F1 / confusion matrix computed by running the pipeline over labelled
   data. Never hard-coded.
5. **Multi-signal forensic analysis** — ELA, noise inconsistency, copy-move,
   boundary and metadata signals, plus reliable **reference-difference** analysis
   ("photo on file") with a visual tamper overlay.
6. **Local synthetic watchlist lookup** — normalised identifier matching against a
   local SQLite watchlist (synthetic records only).
7. **Full audit trail** — every upload, module completion, decision and override
   is logged and shown as a timeline.
8. **Dynamic security-operations dashboard** — all figures come from SQLite; empty
   database shows real zeros, not fabricated numbers.

## 5. Technology Stack

| Layer | Technology |
|-------|-----------|
| Frontend | HTML5, CSS3, **vanilla JavaScript** (no frameworks), Chart.js (bundled locally) |
| Backend | Python 3.11+, **FastAPI**, Uvicorn, Pydantic |
| Database | **SQLite** via SQLAlchemy 2.0 |
| OCR | **Tesseract** (`pytesseract`); PaddleOCR auto-detected if installed |
| MRZ | Pure-Python ICAO 9303 parser + checksum validation (TD1/TD2/TD3) |
| Forensics | OpenCV, Pillow, NumPy, scikit-image |
| Face | **OpenCV YuNet** (detector) + **SFace** (embedder) ONNX models — no dlib |
| Reports | ReportLab (PDF) |
| Risk/Evidence | Deterministic, configurable weights |

No paid APIs. Runs on a normal development laptop.

## 6. System Workflow (pipeline stages)

`Document Received → Classification → OCR → MRZ Validation → Field Consistency →
Forensic Analysis → Face Verification → Watchlist Lookup → Identity Consistency →
Risk Assessment` → **Human Review**.

Each stage persists a **structured result** and reports one of
`WAITING / PROCESSING / COMPLETED / WARNING / FAILED / SKIPPED`. The frontend polls
a real backend status endpoint — progress is never faked with timers.

---

## 7. Installation (Windows)

### Prerequisites
- **Python 3.11+**
- **Tesseract-OCR** installed (default path `C:\Program Files\Tesseract-OCR\`).
  Download: <https://github.com/UB-Mannheim/tesseract/wiki>. The app auto-detects
  it, or set `TESSERACT_CMD` in `.env`.

### One-command start
```bat
run_backend.bat
```
On first run this creates a virtual environment, installs dependencies, generates
the synthetic dataset, seeds demo data, and starts the server. Then open:

- App: <http://127.0.0.1:8000/>
- API docs (OpenAPI/Swagger): <http://127.0.0.1:8000/docs>

### Manual setup
```bat
python -m venv .venv
.venv\Scripts\activate
pip install -r backend\requirements.txt

REM generate the synthetic dataset + seed the demo database
python backend\generate_synthetic_docs.py
cd backend && python seed_demo_data.py && cd ..

REM run (serves the frontend too)
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000
```

`run_frontend.bat` just opens the browser (the FastAPI backend serves the
frontend as static files — no separate frontend server needed).

### Database
SQLite at `data/screening.db`, created automatically. Tables are created on
startup; no migrations required.

### Synthetic dataset
`python backend/generate_synthetic_docs.py` writes paired
`passport_00X_genuine.jpg` / `passport_00X_altered.jpg` documents plus a
`manifest.json` (ground truth) into `data/synthetic/`. You may also drop your own
synthetic documents there. Faces are GAN-synthesised (no real identities).

---

## 8. SIH Demo Script

Seed data first (Settings → *Seed Demo Data*, or `python backend/seed_demo_data.py`).

- **Demo 1 — Genuine passport.** New Screening → upload `passport_001_genuine.jpg`.
  Watch the live pipeline. Result: **LOW** risk, MRZ valid, fields consistent,
  no watchlist match.
- **Demo 2 — Altered passport.** Upload `passport_001_altered.jpg`. Same pipeline,
  changed results: MRZ **checksum failure**, **field mismatch** (DOB) → risk rises
  to **MEDIUM/HIGH**. Open the investigation to see the evidence breakdown.
- **Demo 3 — Watchlist match.** Upload `passport_099_watchlist_demo.jpg`
  (identifier `SP0000099` is in the synthetic watchlist) → **WATCHLIST MATCH**,
  with the reason and risk contribution shown.
- **Demo 4 — Cross-document.** New Screening → tick *Cross-document* and upload two
  documents of the same identity → Investigation → **Cross-Document** tab shows the
  consistency matrix.
- **Demo 5 — Officer review & override.** Open a HIGH/CRITICAL investigation →
  *Officer Review* → choose e.g. `INCONCLUSIVE` with the note *"Insufficient image
  quality for reliable face verification."* → the override + justification are
  recorded and appear in the audit trail.
- **Demo 6 — Evaluation.** Evaluation page → *Run Evaluation* → real accuracy /
  precision / recall / F1 + confusion matrix + per-detector breakdown, computed
  live over the labelled synthetic dataset.

The **face-swap** case is best seen on `passport_002_altered.jpg` /
`passport_004_altered.jpg`: SFace reports a low similarity vs the enrolled
reference, and the Forensics tab highlights the swapped photo region.

## 9. Evaluation Instructions

`POST /api/evaluation/run` (or the Evaluation page) runs every detection module
over `data/synthetic/`, compares predictions against ground truth, and reports:
accuracy, precision, recall, F1, false-positive/negative rates, a confusion matrix,
and a per-detector breakdown (MRZ, Forensics, Field Consistency, Watchlist,
Metadata). Failures are shown honestly as FP/FN.

## 10. API Documentation

Full interactive docs at `/docs`. Highlights:

| Method | Path | Purpose |
|---|---|---|
| GET | `/api/health` | System / engine status |
| POST | `/api/documents/upload` | Upload + (optionally) analyse |
| GET | `/api/analysis/{id}/status` | Live pipeline status (polled) |
| GET | `/api/investigations/{id}` | Full investigation (results/evidence/risk/audit) |
| GET | `/api/investigations` | History with filters/search |
| GET | `/api/compare?a=&b=` | Genuine-vs-altered comparison |
| POST | `/api/reviews` | Record an officer decision |
| GET/POST/PUT/DELETE | `/api/watchlist…` | Synthetic watchlist CRUD + `/search`, `/seed-demo` |
| GET | `/api/dashboard/overview` | Stats + risk distribution + trend + activity |
| POST | `/api/evaluation/run` | Run dataset evaluation |
| POST | `/api/reports/{id}` | Generate a PDF report |
| GET | `/api/cases`, `/api/notifications`, `/api/search` | Cases / notifications / global search |

## 11. Project Structure

```
final-test/
├── backend/
│   ├── app/
│   │   ├── main.py                 # FastAPI app (serves frontend + API)
│   │   ├── config.py               # settings (.env, paths, weights, engines)
│   │   ├── api/                    # REST routers (health, documents, analysis, …)
│   │   ├── services/               # OCR, MRZ, forensic, face, watchlist,
│   │   │                           #   identity, evidence, risk, analysis (orchestrator),
│   │   │                           #   evaluation, report, case, audit, notification, dashboard, demo
│   │   ├── models/                 # SQLAlchemy tables (15+)
│   │   ├── schemas/                # Pydantic requests + JSON serialisers
│   │   ├── database/               # engine / session / init
│   │   ├── core/                   # constants, security (upload validation)
│   │   ├── utils/                  # image + text helpers
│   │   └── models_store/           # YuNet + SFace ONNX + GAN faces (build assets)
│   ├── tests/                      # pytest suite
│   ├── requirements.txt
│   ├── generate_synthetic_docs.py  # synthetic dataset generator
│   └── seed_demo_data.py           # seed / clear / reset CLI
├── frontend/
│   ├── index.html, screening.html, investigation.html, history.html,
│   │   cases.html, watchlist.html, evaluation.html, reports.html, settings.html
│   ├── css/main.css
│   └── js/  (api.js, common.js, dashboard.js, screening.js, investigation.js, …)
├── data/  (synthetic/, uploads/, processed/, reports/, screening.db)
├── .env.example
├── run_backend.bat / run_frontend.bat
└── README.md
```

## 12. Security Considerations

- Upload validation: extension **and** magic-byte checks, size limit, MIME sanity.
- Server-side generated filenames (uploaded names are never trusted).
- Path-traversal protection on all file serving; uploads stored **outside** the
  frontend static directory; uploaded files are never executed.
- OCR text is escaped before display (frontend uses `textContent`/escaping); API
  inputs validated with Pydantic; filesystem paths and secrets are not exposed.
- `.env.example` documents configuration; secrets stay out of the code.

## 13. AI/ML Transparency & Limitations

**Genuinely implemented:** OCR, ICAO 9303 MRZ validation, field consistency,
computer-vision forensics (incl. reference-difference), OpenCV face
detection + verification, watchlist lookup, deterministic evidence + risk engines,
cross-document consistency, live evaluation.

**Honestly limited:**
- Blind passive forensics (ELA/noise/copy-move) is noisy on clean rendered
  documents; it is shown as *informational* and never alone declares tampering.
  A **trained ML tampering model is not configured** (Settings shows this) — the
  `TamperingDetector` interface is ready for one to be plugged in.
- Face verification needs an enrolled reference for 1:1 matching; single documents
  without a reference report `NO_REFERENCE` honestly.
- PDF documents require a rasteriser (PyMuPDF) to analyse images; otherwise the
  pipeline degrades honestly.
- The watchlist is a **local synthetic** table; "no match" never implies genuine.

Swappable abstractions (`DocumentClassifier`, `TamperingDetector`, `FaceVerifier`,
`RiskEngine`) let trained models replace the prototype algorithms without rewrites.

## 14. Future Improvements

- Trained PyTorch tampering-localisation and document-classification models.
- Optional Neo4j-backed identity graph (structure already relational-ready).
- Liveness / additional MRZ document types; ISO-compliant registration for scans.
- Role-based auth and multi-officer workflows.

## 15. Screenshots

Add screenshots of: Dashboard, live New Screening, a CRITICAL Investigation
(evidence + forensic overlay), the Cross-Document matrix, an Officer Review with
override, and the Evaluation confusion matrix. (Capture these from the running
app at 1600×900+.)

## 16. SIH Presentation Talking Points

- "Not OCR + face + fake-detection — an **evidence-driven screening workstation**."
- **Explainability:** every risk point maps to a named evidence item.
- **Human-in-the-loop:** the officer can override; the override is audited.
- **Honesty:** the system says `SKIPPED` / `UNAVAILABLE` rather than faking a
  result, and reports real evaluation numbers including its own failures.
- **Cross-document consistency** and **reference-difference forensics** are the
  standout differentiators.
- Runs fully offline on a laptop, no paid APIs, on synthetic data only.

---

*This is a demonstration prototype built for SIH26188. All documents, identities,
faces and watchlist records are synthetic. The system is an analytical aid; the
authorised officer is responsible for every final decision.*

🤖 Generated with [Claude Code](https://claude.com/claude-code)
