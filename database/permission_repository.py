"""
Permission repository for Phase 3 database access: repository permissions.
"""

from typing import List, Optional

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import RepositoryModel, RepositoryPermissionModel
from utils.logger import logger


class PermissionRepository:
    """Manages repository permissions in SQLite database."""

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def get_permissions(self, repository_id: int) -> RepositoryPermissionModel:
        """
        Get permissions for a repository.
        If no record exists, inserts and returns safe default permissions.
        """
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM repository_permissions WHERE repository_id = ?",
                (repository_id,),
            )
            row = cursor.fetchone()
            if row:
                d = dict(row)
                return RepositoryPermissionModel(
                    repository_id=d["repository_id"],
                    monitoring_enabled=bool(d["monitoring_enabled"]),
                    ai_analysis_enabled=bool(d["ai_analysis_enabled"]),
                    autonomous_development_enabled=bool(d["autonomous_development_enabled"]),
                    smart_commit_enabled=bool(d["smart_commit_enabled"]),
                    auto_commit_enabled=bool(d["auto_commit_enabled"]),
                    remote_push_enabled=bool(d["remote_push_enabled"]),
                    pull_request_creation_enabled=bool(d.get("pull_request_creation_enabled", False)),
                    updated_at=d.get("updated_at"),
                )

        # Default permissions
        default_model = RepositoryPermissionModel(
            repository_id=repository_id,
            monitoring_enabled=True,
            ai_analysis_enabled=True,
            autonomous_development_enabled=False,
            smart_commit_enabled=True,
            auto_commit_enabled=False,
            remote_push_enabled=False,
            pull_request_creation_enabled=False,
            updated_at=get_utc_now_iso(),
        )
        return self.save_permissions(default_model)

    def save_permissions(self, model: RepositoryPermissionModel) -> RepositoryPermissionModel:
        """Insert or replace permissions record."""
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO repository_permissions (
                    repository_id,
                    monitoring_enabled,
                    ai_analysis_enabled,
                    autonomous_development_enabled,
                    smart_commit_enabled,
                    auto_commit_enabled,
                    remote_push_enabled,
                    pull_request_creation_enabled,
                    updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                    monitoring_enabled=excluded.monitoring_enabled,
                    ai_analysis_enabled=excluded.ai_analysis_enabled,
                    autonomous_development_enabled=excluded.autonomous_development_enabled,
                    smart_commit_enabled=excluded.smart_commit_enabled,
                    auto_commit_enabled=excluded.auto_commit_enabled,
                    remote_push_enabled=excluded.remote_push_enabled,
                    pull_request_creation_enabled=excluded.pull_request_creation_enabled,
                    updated_at=excluded.updated_at
                """,
                (
                    model.repository_id,
                    int(model.monitoring_enabled),
                    int(model.ai_analysis_enabled),
                    int(model.autonomous_development_enabled),
                    int(model.smart_commit_enabled),
                    int(model.auto_commit_enabled),
                    int(model.remote_push_enabled),
                    int(model.pull_request_creation_enabled),
                    now,
                ),
            )
        model.updated_at = now
        return model

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
        """Update selective permissions for a repository."""
        current = self.get_permissions(repository_id)
        if monitoring_enabled is not None:
            current.monitoring_enabled = monitoring_enabled
        if ai_analysis_enabled is not None:
            current.ai_analysis_enabled = ai_analysis_enabled
        if autonomous_development_enabled is not None:
            current.autonomous_development_enabled = autonomous_development_enabled
        if smart_commit_enabled is not None:
            current.smart_commit_enabled = smart_commit_enabled
        if auto_commit_enabled is not None:
            current.auto_commit_enabled = auto_commit_enabled
        if remote_push_enabled is not None:
            current.remote_push_enabled = remote_push_enabled
        if pull_request_creation_enabled is not None:
            current.pull_request_creation_enabled = pull_request_creation_enabled

        return self.save_permissions(current)

    def revoke_all(self, repository_id: int) -> RepositoryPermissionModel:
        """Revoke all permissions for a repository."""
        return self.update_permissions(
            repository_id=repository_id,
            monitoring_enabled=False,
            ai_analysis_enabled=False,
            autonomous_development_enabled=False,
            smart_commit_enabled=False,
            auto_commit_enabled=False,
            remote_push_enabled=False,
            pull_request_creation_enabled=False,
        )

    def list_authorized_repositories(
        self, required_permission: Optional[str] = None
    ) -> List[RepositoryModel]:
        """
        List repositories that have a specific permission enabled.
        If required_permission is None, returns all registered repositories that have monitoring_enabled.
        """
        column_map = {
            "monitoring": "monitoring_enabled",
            "ai_analysis": "ai_analysis_enabled",
            "autonomous_development": "autonomous_development_enabled",
            "smart_commit": "smart_commit_enabled",
            "auto_commit": "auto_commit_enabled",
            "remote_push": "remote_push_enabled",
            "pull_request_creation": "pull_request_creation_enabled",
        }
        col = column_map.get(required_permission or "monitoring", "monitoring_enabled")

        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT r.* FROM repositories r
                JOIN repository_permissions p ON r.id = p.repository_id
                WHERE p.{col} = 1
                ORDER BY r.id ASC
                """
            )
            rows = cursor.fetchall()
            return [RepositoryModel(**dict(r)) for r in rows]

