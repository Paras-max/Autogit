@echo off
:: ============================================================
::  AutoGit AI – Windows One-Click Launcher
::  Starts the FastAPI backend and opens the dashboard browser.
:: ============================================================

title AutoGit AI

echo.
echo  =========================================
echo   AutoGit AI  v0.4.0  -  Phase 4
echo   IDE-Independent Autonomous Git Agent
echo  =========================================
echo.

:: Locate Python from the venv if present, else system Python
if exist "%~dp0.venv\Scripts\python.exe" (
    set PYTHON="%~dp0.venv\Scripts\python.exe"
) else if exist "%~dp0venv\Scripts\python.exe" (
    set PYTHON="%~dp0venv\Scripts\python.exe"
) else (
    set PYTHON=python
)

:: Confirm python is available
%PYTHON% --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found. Please install Python 3.11+ or activate your virtual environment.
    pause
    exit /b 1
)

:: Load .env if present (best-effort: values are picked up by python-dotenv at runtime)
if exist "%~dp0.env" (
    echo [INFO] .env file found – will be loaded by the application.
)

echo [INFO] Starting AutoGit AI backend on http://127.0.0.1:8000 ...
echo [INFO] Press Ctrl+C in this window to stop the server.
echo.

:: Open the dashboard in the default browser after a short delay
start "" /B powershell -NoProfile -Command "Start-Sleep 3; Start-Process 'http://127.0.0.1:8000'"

:: Start the FastAPI backend (blocking)
%PYTHON% -m uvicorn main:app --host 127.0.0.1 --port 8000 --reload

pause
