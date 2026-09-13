@echo off
REM ==========================================================================
REM  SENTINEL - AI-Based Fake Identity & Document Screening System (SIH26188)
REM  Starts the FastAPI backend (also serves the frontend) at
REM      http://127.0.0.1:8000
REM ==========================================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo Creating virtual environment .venv ...
    python -m venv .venv
    call .venv\Scripts\activate.bat
    echo Installing dependencies ...
    python -m pip install --upgrade pip
    python -m pip install -r backend\requirements.txt
) else (
    call .venv\Scripts\activate.bat
)

REM First run: create tables + seed the synthetic demo if the DB is missing.
if not exist "data\screening.db" (
    echo Generating synthetic dataset and seeding demo data ...
    python backend\generate_synthetic_docs.py
    pushd backend
    python seed_demo_data.py
    popd
)

echo.
echo ============================================================
echo   SENTINEL backend running at  http://127.0.0.1:8000
echo   API docs:                    http://127.0.0.1:8000/docs
echo   DEMO MODE - SYNTHETIC DOCUMENTS ONLY
echo ============================================================
echo.
python -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 --reload
pause
