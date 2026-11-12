"""
Repository Manager for AutoGit AI.
Manages repository registration, validation, SQLite persistence, and metadata extraction.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from core.git_manager import GitManager
from database.db import DatabaseManager, db as default_db
from database.models import RepositoryModel
from utils.logger import logger
from utils.validators import validate_is_git_repository, validate_local_path


class RepositoryManager:
    """
    Manages repository registration, retrieval, removal, and validation.
    Stores metadata in SQLite. Never initializes or modifies repository files.
    """

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def validate_repository(self, path_str: str) -> Tuple[bool, Optional[str], Optional[Path]]:
        """
        Validate whether the given path exists, is a directory, and contains a valid Git repo.
        Returns: (is_valid, error_message, resolved_path)
        """
        is_path_valid, path_err, resolved = validate_local_path(path_str)
        if not is_path_valid:
            return False, path_err, None

        assert resolved is not None
        is_git_valid, git_err = validate_is_git_repository(resolved)
        if not is_git_valid:
            return False, git_err, None

        # Verify that GitPython can read it
        try:
            GitManager(resolved)
        except Exception as e:
            return False, f"Git repository check failed: {e}", None

        return True, None, resolved

    def add_repository(
        self,
        path: str,
        name: Optional[str] = None,
    ) -> RepositoryModel:
        """
        Register a new local Git repository.
        Validates path, queries current Git metadata, and records in SQLite.
        """
        is_valid, error_msg, resolved_path = self.validate_repository(path)
        if not is_valid:
            logger.warning(f"Failed to register repository '{path}': {error_msg}")
            raise ValueError(error_msg)

        assert resolved_path is not None
        resolved_str = str(resolved_path)

        # Check if already registered
        existing = self.db.get_repository_by_path(resolved_str)
        if existing:
            logger.info(f"Repository already registered: {resolved_str} (ID {existing.id})")
            return existing

        # Extract repo name and metadata
        repo_name = name.strip() if name and name.strip() else resolved_path.name
        git_mgr = GitManager(resolved_path)
        current_branch = git_mgr.get_current_branch()
        remote_url = git_mgr.get_remote_url()

        repo_record = self.db.add_repository(
            name=repo_name,
            path=resolved_str,
            remote_url=remote_url,
            current_branch=current_branch,
        )
        logger.info(
            f"Successfully registered repository '{repo_name}' (ID: {repo_record.id}) at '{resolved_str}'"
        )
        return repo_record

    def remove_repository(self, repo_id: int) -> bool:
        """
        Remove repository from AutoGit AI management without touching underlying files.
        """
        repo = self.db.get_repository(repo_id)
        if not repo:
            logger.warning(f"Cannot remove: Repository ID {repo_id} not found")
            return False

        success = self.db.remove_repository(repo_id)
        if success:
            logger.info(
                f"Removed repository '{repo.repository_name}' (ID: {repo_id}) from application"
            )
        return success

    def get_repository_info(self, repo_id: int) -> Optional[Dict[str, Any]]:
        """
        Retrieve repository record along with real-time Git metadata and latest commit.
        """
        repo = self.db.get_repository(repo_id)
        if not repo:
            return None

        # Live git details
        try:
            git_mgr = GitManager(repo.repository_path)
            current_branch = git_mgr.get_current_branch()
            remote_url = git_mgr.get_remote_url()
            latest_commit = git_mgr.get_latest_commit()

            # Refresh DB branch/remote if changed
            if current_branch != repo.current_branch or remote_url != repo.remote_url:
                repo = self.db.update_repository(
                    repo_id=repo.id,  # type: ignore
                    remote_url=remote_url,
                    current_branch=current_branch,
                ) or repo
        except Exception as e:
            logger.warning(f"Failed to fetch live Git info for repo ID {repo_id}: {e}")
            latest_commit = None

        return {
            "id": repo.id,
            "repository_name": repo.repository_name,
            "repository_path": repo.repository_path,
            "remote_url": repo.remote_url,
            "current_branch": repo.current_branch,
            "created_at": repo.created_at,
            "latest_commit": latest_commit,
        }

    def list_repositories(self) -> List[RepositoryModel]:
        """List all registered repositories."""
        return self.db.list_repositories()

