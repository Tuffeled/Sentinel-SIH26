@echo off
REM ==========================================================================
REM  The FastAPI backend already serves the frontend at http://127.0.0.1:8000
REM  This script simply opens it in the default browser.
REM  (Run run_backend.bat first.)
REM ==========================================================================
echo Opening SENTINEL at http://127.0.0.1:8000 ...
start "" "http://127.0.0.1:8000"
