"""
Repository permission management and authorization enforcement for AutoGit AI (Phase 3).
Ensures that AutoGit AI only accesses, analyzes, or modifies repositories explicitly authorized by the user.
"""

from typing import Any, Dict, List, Optional

from database.db import DatabaseManager, db as default_db
from database.models import RepositoryModel, RepositoryPermissionModel
from database.permission_repository import PermissionRepository
from utils.logger import logger


class PermissionDeniedError(Exception):
    """Raised when an operation is attempted on an unauthorized repository or without required permission."""
    pass


class PermissionManager:
    """
    Manages and enforces repository-level permissions.
    Default policy:
    - monitoring: enabled for registered repos
    - ai_analysis: enabled for registered repos
    - autonomous_development: DISABLED by default (requires explicit user opt-in)
    - smart_commit: enabled (requires human approval)
    - auto_commit: DISABLED by default
    - remote_push: DISABLED by default
    """

    PERMISSION_MAP = {
        "monitoring": "monitoring_enabled",
        "ai_analysis": "ai_analysis_enabled",
        "autonomous_development": "autonomous_development_enabled",
        "smart_commit": "smart_commit_enabled",
        "auto_commit": "auto_commit_enabled",
        "remote_push": "remote_push_enabled",
        "pull_request_creation": "pull_request_creation_enabled",
    }

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        permission_repo: Optional[PermissionRepository] = None,
    ):
        self.db = database or default_db
        self.permission_repo = permission_repo or PermissionRepository(self.db)

    def get_permissions(self, repository_id: int) -> RepositoryPermissionModel:
        """Retrieve current permissions for a repository."""
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository with id {repository_id} does not exist.")
        return self.permission_repo.get_permissions(repository_id)

    def update_permissions(
        self,
        repository_id: int,
        monitoring_enabled: Optional[bool] = None,
        ai_analysis_enabled: Optional[bool] = None,
        autonomous_development_enabled: Optional[bool] = None,
        smart_commit_enabled: Optional[bool] = None,
        auto_commit_enabled: Optional[bool] = None,
        remote_push_enabled: Optional[bool] = None,
        pull_request_creation_enabled: Optional[bool] = None,
    ) -> RepositoryPermissionModel:
        """Update permissions for a repository."""
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository with id {repository_id} does not exist.")

        updated = self.permission_repo.update_permissions(
            repository_id=repository_id,
            monitoring_enabled=monitoring_enabled,
            ai_analysis_enabled=ai_analysis_enabled,
            autonomous_development_enabled=autonomous_development_enabled,
            smart_commit_enabled=smart_commit_enabled,
            auto_commit_enabled=auto_commit_enabled,
            remote_push_enabled=remote_push_enabled,
            pull_request_creation_enabled=pull_request_creation_enabled,
        )
        logger.info(
            f"Permissions updated for repository {repository_id} ({repo.repository_name}): "
            f"dev={updated.autonomous_development_enabled}, auto_commit={updated.auto_commit_enabled}, pr={updated.pull_request_creation_enabled}"
        )
        return updated

    def verify_permission(self, repository_id: int, permission_name: str) -> bool:
        """
        Verify if a repository has a specific permission enabled.
        Returns False if repository doesn't exist or permission is not enabled.
        """
        attr_name = self.PERMISSION_MAP.get(permission_name)
        if not attr_name:
            raise ValueError(f"Unknown permission '{permission_name}'. Valid permissions: {list(self.PERMISSION_MAP.keys())}")

        try:
            perms = self.get_permissions(repository_id)
            return bool(getattr(perms, attr_name, False))
        except Exception as e:
            logger.warning(f"Failed to verify permission '{permission_name}' for repo {repository_id}: {e}")
            return False

    def assert_permission(self, repository_id: int, permission_name: str) -> None:
        """
        Assert that a repository has a specific permission enabled.
        Raises PermissionDeniedError if not authorized.
        """
        if not self.verify_permission(repository_id, permission_name):
            repo = self.db.get_repository(repository_id)
            repo_name = repo.repository_name if repo else f"ID {repository_id}"
            raise PermissionDeniedError(
                f"Repository '{repo_name}' is not authorized for '{permission_name}'. "
                f"Please grant this permission before executing this action."
            )

    def enable_autonomous_development(self, repository_id: int) -> RepositoryPermissionModel:
        """Explicitly enable autonomous development for a repository."""
        return self.update_permissions(repository_id, autonomous_development_enabled=True)

    def disable_autonomous_development(self, repository_id: int) -> RepositoryPermissionModel:
        """Disable autonomous development for a repository."""
        return self.update_permissions(repository_id, autonomous_development_enabled=False)

    def revoke_all_permissions(self, repository_id: int) -> RepositoryPermissionModel:
        """Revoke all permissions for a repository."""
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository with id {repository_id} does not exist.")
        revoked = self.permission_repo.revoke_all(repository_id)
        logger.warning(f"All permissions REVOKED for repository {repository_id} ({repo.repository_name}).")
        return revoked

    def get_authorized_repositories(self, action: str = "monitoring") -> List[RepositoryModel]:
        """List all repositories authorized for a specific action."""
        return self.permission_repo.list_authorized_repositories(action)

