"""
Safe Code Modifier for AutoGit AI (Phase 3).
Executes code modifications within repository or isolated worktree with strict safety controls,
path traversal checks, syntax verification, and snapshot rollback.
"""

import ast
import json
from pathlib import Path
from typing import Any, Dict, List, Optional

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import DevelopmentChangeModel
from utils.logger import logger


# Forbidden file patterns that AutoGit AI must NEVER create or modify
FORBIDDEN_PATTERNS = [
    ".env",
    ".git",
    "id_rsa",
    "id_ed25519",
    ".pem",
    ".key",
    "credentials",
    "secrets.json",
    "token",
    "private_key",
]


class CodeModificationError(Exception):
    """Raised when a code modification fails validation, syntax check, or safety rules."""
    pass


class CodeModifier:
    """
    Safely executes and rolls back code modifications.
    Enforces syntax validation and prevents accidental modification of sensitive files.
    """

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def is_file_allowed(self, target_file: str, base_dir: Path) -> bool:
        """Verify that the target file is safe to modify and inside base_dir."""
        target_path = (base_dir / target_file).resolve()
        base_resolved = base_dir.resolve()

        # Path traversal guard
        try:
            target_path.relative_to(base_resolved)
        except ValueError:
            logger.warning(f"Rejected path traversal attempt: {target_file}")
            return False

        lower_name = target_path.name.lower()
        for forbidden in FORBIDDEN_PATTERNS:
            if forbidden in lower_name or forbidden in str(target_path).lower():
                logger.warning(f"Forbidden file pattern detected: {target_file}")
                return False

        return True

    def validate_syntax(self, file_path: Path, content: str) -> None:
        """
        Validate file syntax before persisting changes.
        Supports Python AST validation and JSON validation.
        """
        suffix = file_path.suffix.lower()
        if suffix == ".py":
            try:
                ast.parse(content, filename=str(file_path))
            except SyntaxError as e:
                raise CodeModificationError(
                    f"Syntax error in generated Python code for {file_path.name}: {e}"
                ) from e
        elif suffix == ".json":
            try:
                json.loads(content)
            except json.JSONDecodeError as e:
                raise CodeModificationError(
                    f"Invalid JSON content for {file_path.name}: {e}"
                ) from e

    def apply_file_change(
        self,
        base_dir: Path,
        relative_file: str,
        content: str,
        session_id: Optional[int] = None,
        description: Optional[str] = None,
    ) -> DevelopmentChangeModel:
        """
        Safely apply content change to a file.
        Creates parent directories if necessary.
        Rolls back on syntax or writing error.
        """
        base_dir = Path(base_dir).resolve()
        if not self.is_file_allowed(relative_file, base_dir):
            raise CodeModificationError(
                f"Modification blocked: Target file '{relative_file}' violates safety policies."
            )

        target_path = (base_dir / relative_file).resolve()
        change_type = "modified" if target_path.exists() else "created"
        previous_content: Optional[str] = None

        if target_path.exists():
            try:
                previous_content = target_path.read_text(encoding="utf-8", errors="ignore")
            except Exception as e:
                logger.warning(f"Could not read previous file content: {e}")

        # Validate syntax of new content
        self.validate_syntax(target_path, content)

        # Apply modification
        try:
            target_path.parent.mkdir(parents=True, exist_ok=True)
            target_path.write_text(content, encoding="utf-8")
        except Exception as e:
            # Rollback
            if previous_content is not None:
                target_path.write_text(previous_content, encoding="utf-8")
            elif target_path.exists():
                target_path.unlink(missing_ok=True)
            raise CodeModificationError(f"Failed writing to {relative_file}: {e}") from e

        # Record change in database if session_id is provided
        diff_snippet = f"--- /dev/null\n+++ {relative_file}\n{content[:300]}" if change_type == "created" else f"Modified {relative_file}"
        change_model = DevelopmentChangeModel(
            id=None,
            session_id=session_id or 0,
            file_path=relative_file,
            change_type=change_type,
            description=description or f"Applied {change_type} to {relative_file}",
            diff_snippet=diff_snippet,
        )

        if session_id:
            with self.db.get_cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO development_changes (session_id, file_path, change_type, description, diff_snippet)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, relative_file, change_type, description, diff_snippet),
                )
                change_model.id = cursor.lastrowid

        logger.info(f"Successfully {change_type} '{relative_file}' in {base_dir}")
        return change_model

