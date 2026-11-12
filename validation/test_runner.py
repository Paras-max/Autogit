"""
Automated Test Runner for AutoGit AI.
Detects and executes existing project test suites safely without auto-installing dependencies.
"""

from pathlib import Path
import time
from typing import Any, Dict, Optional

from utils.logger import logger
from utils.security import safe_subprocess_run


class TestRunner:
    """Executes existing project tests safely."""

    __test__ = False

    def __init__(self, default_timeout: float = 60.0):
        self.default_timeout = default_timeout

    def detect_test_command(self, repo_path: Path) -> Optional[list[str]]:
        """Identify available test frameworks in the repository."""
        # 1. Python pytest
        if (repo_path / "pytest.ini").exists() or (repo_path / "tests").exists() or (repo_path / "conftest.py").exists():
            # Check virtualenv python first if present
            venv_python_win = repo_path / ".venv" / "Scripts" / "python.exe"
            venv_python_nix = repo_path / ".venv" / "bin" / "python"
            if venv_python_win.exists():
                return [str(venv_python_win), "-m", "pytest", "-q"]
            elif venv_python_nix.exists():
                return [str(venv_python_nix), "-m", "pytest", "-q"]
            return ["python", "-m", "pytest", "-q"]

        # 2. Node npm test
        if (repo_path / "package.json").exists():
            return ["npm", "test"]

        # 3. Rust cargo test
        if (repo_path / "Cargo.toml").exists():
            return ["cargo", "test"]

        # 4. Go test
        if (repo_path / "go.mod").exists():
            return ["go", "test", "./..."]

        return None

    def run_tests(
        self, repo_path: Path | str, timeout: Optional[float] = None
    ) -> Dict[str, Any]:
        path = Path(repo_path).resolve()
        cmd = self.detect_test_command(path)

        if not cmd:
            logger.info(f"No recognized test suite found in {path}. Skipping test execution.")
            return {
                "status": "SKIPPED",
                "output": "No configured test suite detected.",
                "duration": 0.0,
                "passed": 0,
                "failed": 0,
            }

        start_time = time.time()
        timeout_val = timeout or self.default_timeout
        logger.info(f"Executing test command: {' '.join(cmd)} (timeout={timeout_val}s)")

        exit_code, stdout, stderr = safe_subprocess_run(
            cmd_args=cmd, cwd=path, timeout=timeout_val
        )
        duration = round(time.time() - start_time, 2)

        output = (stdout + "\n" + stderr).strip()
        status = "PASSED" if exit_code == 0 else "FAILED"

        logger.info(f"Tests finished with status: {status} in {duration}s")
        return {
            "status": status,
            "exit_code": exit_code,
            "output": output[:2000],  # truncated summary
            "duration": duration,
        }

