"""
Git Execution Engine for AutoGit AI.
Executes controlled Git operations, verifies commits, and enforces safety boundaries.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.credential_manager import CredentialManager
from core.git_manager import GitManager
from core.staging_manager import StagingManager
from database.db import DatabaseManager, db as default_db
from database.models import RepositoryAutomationSettingsModel
from utils.logger import logger
from utils.security import safe_subprocess_run


class GitExecutor:
    """Safely creates and verifies commits on behalf of AutoGit AI."""

    def __init__(
        self,
        repo_path: Path | str,
        database: Optional[DatabaseManager] = None,
        cred_manager: Optional[CredentialManager] = None,
    ):
        self.repo_path = Path(repo_path).resolve()
        self.db = database or default_db
        self.cred_mgr = cred_manager or CredentialManager(self.db)
        self.git_mgr = GitManager(self.repo_path)
        self.staging_mgr = StagingManager(self.repo_path)

    def verify_commit_exists(self, commit_hash: str) -> bool:
        """Verify that the commit hash actually exists in the Git repository."""
        if not commit_hash or len(commit_hash) < 7:
            return False
        exit_code, stdout, _ = safe_subprocess_run(
            ["git", "cat-file", "-t", commit_hash], cwd=self.repo_path, timeout=5.0
        )
        return exit_code == 0 and stdout.strip() == "commit"

    def execute_commit(
        self,
        files_to_commit: List[str],
        commit_message: str,
        settings: RepositoryAutomationSettingsModel,
    ) -> Dict[str, Any]:
        """
        Execute pre-validated commit for the approved files.
        Guarantees commit verification and safe non-destructive staging.
        """
        if not files_to_commit:
            return {
                "success": False,
                "commit_hash": None,
                "error": "Cannot execute commit with an empty file list.",
            }

        if not commit_message or not commit_message.strip():
            return {
                "success": False,
                "commit_hash": None,
                "error": "Cannot execute commit with an empty commit message.",
            }

        # Check current branch
        current_branch = self.git_mgr.get_current_branch()
        is_protected = current_branch.lower() in [
            b.lower() for b in settings.protected_branches
        ]
        if is_protected and settings.execution_mode == "auto":
            return {
                "success": False,
                "commit_hash": None,
                "error": f"Auto Commit blocked on protected branch '{current_branch}'.",
            }

        # Resolve Git author identity (application override or Git config)
        identity = self.cred_mgr.get_git_identity(str(self.repo_path))
        author_name = identity.get("name") or "AutoGit AI"
        author_email = identity.get("email") or "autogit@ai.local"

        logger.info(
            f"Executing commit for {len(files_to_commit)} file(s) on branch '{current_branch}' by {author_name}"
        )

        # Execute commit using isolated index to guarantee zero disruption to developer's index
        success, commit_hash, error_msg = self.staging_mgr.commit_with_isolated_index(
            files_to_commit=files_to_commit,
            commit_message=commit_message.strip(),
            author_name=author_name,
            author_email=author_email,
        )

        if not success or not commit_hash:
            logger.error(f"Commit execution failed: {error_msg}")
            return {
                "success": False,
                "commit_hash": None,
                "error": error_msg or "Failed to create commit.",
            }

        # Verify commit exists in repository object database
        if not self.verify_commit_exists(commit_hash):
            logger.critical(f"Commit verification failed for hash: {commit_hash}")
            return {
                "success": False,
                "commit_hash": commit_hash,
                "error": "Commit created but failed post-commit existence verification.",
            }

        logger.info(f"Commit verified successfully: {commit_hash[:7]}")
        return {
            "success": True,
            "commit_hash": commit_hash,
            "short_hash": commit_hash[:7],
            "committed_files": files_to_commit,
            "commit_message": commit_message.strip(),
            "branch": current_branch,
            "error": None,
        }

