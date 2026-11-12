"""
Build Runner for AutoGit AI.
Executes non-destructive project build or syntax validation commands.
"""

from pathlib import Path
import time
from typing import Any, Dict, Optional

from utils.security import safe_subprocess_run


class BuildRunner:
    """Runs build checks for supported projects."""

    def __init__(self, default_timeout: float = 60.0):
        self.default_timeout = default_timeout

    def detect_build_command(self, repo_path: Path) -> Optional[list[str]]:
        if (repo_path / "Cargo.toml").exists():
            return ["cargo", "check"]
        if (repo_path / "tsconfig.json").exists() and (repo_path / "node_modules").exists():
            return ["npx", "tsc", "--noEmit"]
        return None

    def run_build(self, repo_path: Path | str, timeout: Optional[float] = None) -> Dict[str, Any]:
        path = Path(repo_path).resolve()
        cmd = self.detect_build_command(path)

        if not cmd:
            return {
                "status": "SKIPPED",
                "output": "No build check command configured.",
                "duration": 0.0,
            }

        start_time = time.time()
        exit_code, stdout, stderr = safe_subprocess_run(
            cmd_args=cmd, cwd=path, timeout=timeout or self.default_timeout
        )
        duration = round(time.time() - start_time, 2)
        output = (stdout + "\n" + stderr).strip()

        status = "PASSED" if exit_code == 0 else "FAILED"
        return {
            "status": status,
            "exit_code": exit_code,
            "output": output[:2000],
            "duration": duration,
        }

