#!/usr/bin/env python3
"""
AutoGit AI – Cross-Platform Launcher (run_app.py)

Usage:
    python run_app.py              # Start backend + open browser
    python run_app.py --no-browser # Backend only (headless / server mode)
    python run_app.py --port 9000  # Custom port
"""

import argparse
import os
import platform
import subprocess
import sys
import threading
import time
from pathlib import Path


# ─── Helpers ──────────────────────────────────────────────────────────────────

def find_python() -> str:
    """Return the best available python executable."""
    base = Path(__file__).parent
    candidates = [
        base / ".venv" / "Scripts" / "python.exe",    # Windows venv
        base / ".venv" / "bin" / "python",             # Unix venv
        base / "venv"  / "Scripts" / "python.exe",
        base / "venv"  / "bin" / "python",
    ]
    for candidate in candidates:
        if candidate.exists():
            return str(candidate)
    return sys.executable  # fall back to the python that is running this script


def open_browser(url: str, delay: float = 2.5) -> None:
    """Open url in the default browser after a short delay."""
    time.sleep(delay)
    system = platform.system()
    try:
        if system == "Windows":
            os.startfile(url)  # type: ignore[attr-defined]
        elif system == "Darwin":
            subprocess.Popen(["open", url])
        else:
            subprocess.Popen(["xdg-open", url])
    except Exception as exc:
        print(f"[WARN] Could not open browser automatically: {exc}")
        print(f"       Navigate to {url} manually.")


def print_banner(host: str, port: int) -> None:
    print()
    print("  ╔══════════════════════════════════════════════╗")
    print("  ║          AutoGit AI  v0.4.0  Phase 4        ║")
    print("  ║   IDE-Independent Autonomous Git Agent       ║")
    print("  ╚══════════════════════════════════════════════╝")
    print()
    print(f"  Dashboard  →  http://{host}:{port}")
    print(f"  API Docs   →  http://{host}:{port}/docs")
    print()
    print("  Press Ctrl+C to stop the server.")
    print()


# ─── Main ─────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="AutoGit AI launcher")
    parser.add_argument("--host", default="127.0.0.1", help="Bind host (default: 127.0.0.1)")
    parser.add_argument("--port", default=8000, type=int, help="Bind port (default: 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    parser.add_argument("--reload", action="store_true", default=False,
                        help="Enable Uvicorn auto-reload (development mode)")
    args = parser.parse_args()

    # Change to project root so imports resolve correctly
    project_root = Path(__file__).parent.resolve()
    os.chdir(project_root)

    python_exe = find_python()
    url = f"http://{args.host}:{args.port}"

    print_banner(args.host, args.port)

    # Open browser in a background thread
    if not args.no_browser:
        threading.Thread(target=open_browser, args=(url,), daemon=True).start()

    # Build uvicorn command
    cmd = [
        python_exe, "-m", "uvicorn",
        "main:app",
        "--host", args.host,
        "--port", str(args.port),
    ]
    if args.reload:
        cmd.append("--reload")

    try:
        subprocess.run(cmd, check=True)
    except KeyboardInterrupt:
        print("\n[INFO] AutoGit AI stopped.")
    except subprocess.CalledProcessError as exc:
        print(f"[ERROR] Server exited with code {exc.returncode}")
        sys.exit(exc.returncode)


if __name__ == "__main__":
    main()
