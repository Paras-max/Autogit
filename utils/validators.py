"""
Validation utilities for AutoGit AI.
"""

from pathlib import Path
import re
from typing import Optional, Tuple


EMAIL_REGEX = re.compile(r"^[\w\.\+\-]+@[a-zA-Z0-9\-]+\.[a-zA-Z0-9\-\.]+$")


def validate_local_path(path_str: str) -> Tuple[bool, Optional[str], Optional[Path]]:
    """
    Validate if a given path exists and is a directory.
    Returns (is_valid, error_message, resolved_path).
    """
    if not path_str or not path_str.strip():
        return False, "Path cannot be empty", None

    try:
        resolved = Path(path_str).resolve()
        if not resolved.exists():
            return False, f"Path does not exist: {resolved}", None
        if not resolved.is_dir():
            return False, f"Path is not a directory: {resolved}", None
        return True, None, resolved
    except Exception as e:
        return False, f"Invalid path syntax: {e}", None


def validate_is_git_repository(path: Path) -> Tuple[bool, Optional[str]]:
    """
    Check if a directory is a Git repository (has .git directory or worktree).
    """
    git_dir = path / ".git"
    if not git_dir.exists():
        return False, f"Directory is not a Git repository (no .git found): {path}"
    return True, None


def validate_email(email: str) -> bool:
    """Validate email address format."""
    if not email:
        return False
    return bool(EMAIL_REGEX.match(email.strip()))


def mask_secret(secret: Optional[str], visible_chars: int = 4) -> Optional[str]:
    """
    Mask a sensitive secret, displaying only the first 3 chars and last visible_chars.
    Example: 'ghp_1234567890abcdef' -> 'ghp_...cdef'
    """
    if not secret:
        return None
    secret = secret.strip()
    if len(secret) <= (visible_chars + 3):
        return "***"
    prefix = secret[:3]
    suffix = secret[-visible_chars:]
    return f"{prefix}...{suffix}"

