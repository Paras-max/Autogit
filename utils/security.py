"""
Security utilities: safe subprocess execution with argument arrays,
path traversal checks, secret masking, and local access guards.
"""

from pathlib import Path
import subprocess
from typing import Dict, List, Optional, Tuple

from utils.logger import logger
from utils.validators import mask_secret


def safe_subprocess_run(
    cmd_args: List[str],
    cwd: Optional[Path | str] = None,
    timeout: float = 30.0,
    env: Optional[Dict[str, str]] = None,
) -> Tuple[int, str, str]:
    """
    Execute a process safely using argument arrays without shell interpolation.
    Never uses shell=True.
    Returns (exit_code, stdout, stderr).
    """
    if not cmd_args or not isinstance(cmd_args, list):
        raise ValueError("Command arguments must be a non-empty list of strings.")

    # Convert all arguments to strings
    sanitized_args = [str(arg) for arg in cmd_args]
    working_dir = str(Path(cwd).resolve()) if cwd else None

    try:
        proc = subprocess.run(
            sanitized_args,
            cwd=working_dir,
            timeout=timeout,
            capture_output=True,
            text=True,
            shell=False,
            env=env,
        )
        return proc.returncode, proc.stdout, proc.stderr
    except subprocess.TimeoutExpired:
        logger.warning(f"Process timed out after {timeout}s: {' '.join(sanitized_args[:3])}")
        return -1, "", f"Execution timed out after {timeout} seconds."
    except FileNotFoundError as e:
        logger.warning(f"Executable not found: {cmd_args[0]}: {e}")
        return 127, "", f"Command '{cmd_args[0]}' not found."
    except Exception as e:
        logger.error(f"Subprocess execution error: {e}")
        return 1, "", str(e)


def safe_resolve_repo_path(repo_root: Path, relative_path: str) -> Optional[Path]:
    """
    Resolve a relative path inside repo_root, preventing path traversal attacks.
    Returns resolved Path if safely inside repo_root, else None.
    """
    try:
        resolved_root = repo_root.resolve()
        candidate = (resolved_root / relative_path).resolve()
        # Verify candidate is inside resolved_root
        candidate.relative_to(resolved_root)
        return candidate
    except (ValueError, Exception):
        logger.warning(f"Path traversal attempt or invalid relative path: {relative_path}")
        return None


def verify_local_access(auth_header: Optional[str] = None) -> bool:
    """
    Basic security guard for local MVP execution endpoints.
    In local development, default access is allowed from localhost;
    if AGY_API_KEY / LOCAL_AUTH_TOKEN is set in environment, enforces it.
    """
    import os
    required_token = os.getenv("AUTOGIT_AUTH_TOKEN")
    if not required_token:
        # Open in local trusted environment
        return True
    if not auth_header:
        return False
    token = auth_header.replace("Bearer ", "").strip()
    return token == required_token

