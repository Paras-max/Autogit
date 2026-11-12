"""
Lint Runner for AutoGit AI.
Executes project-configured linters (Ruff, Flake8, ESLint) if installed, without auto-installing.
"""

from pathlib import Path
import shutil
import time
from typing import Any, Dict, Optional

from utils.logger import logger
from utils.security import safe_subprocess_run


class LintRunner:
    """Runs available linters safely."""

    def __init__(self, default_timeout: float = 30.0):
        self.default_timeout = default_timeout

    def detect_linter(self, repo_path: Path) -> Optional[list[str]]:
        # Check ruff in repo venv or PATH
        venv_ruff_win = repo_path / ".venv" / "Scripts" / "ruff.exe"
        if venv_ruff_win.exists():
            return [str(venv_ruff_win), "check", "."]
        if shutil.which("ruff"):
            return ["ruff", "check", "."]

        # Check flake8
        venv_flake8_win = repo_path / ".venv" / "Scripts" / "flake8.exe"
        if venv_flake8_win.exists():
            return [str(venv_flake8_win), "."]
        if shutil.which("flake8"):
            return ["flake8", "."]

        return None

    def run_lint(self, repo_path: Path | str, timeout: Optional[float] = None) -> Dict[str, Any]:
        path = Path(repo_path).resolve()
        cmd = self.detect_linter(path)

        if not cmd:
            return {
                "status": "SKIPPED",
                "output": "No installed linter detected.",
                "duration": 0.0,
            }

        start_time = time.time()
        exit_code, stdout, stderr = safe_subprocess_run(
            cmd_args=cmd, cwd=path, timeout=timeout or self.default_timeout
        )
        duration = round(time.time() - start_time, 2)
        output = (stdout + "\n" + stderr).strip()

        status = "PASSED" if exit_code == 0 else "WARNING"
        return {
            "status": status,
            "exit_code": exit_code,
            "output": output[:2000],
            "duration": duration,
        }

