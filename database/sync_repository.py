"""
Sync repository for Phase 4 database access: GitHub sync history and remote repository status.
"""

from typing import List, Optional

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import GitHubSyncHistoryModel, RemoteRepositoryStatusModel
from utils.logger import logger


class SyncRepository:
    """Manages GitHub sync history and remote status records in SQLite."""

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def get_remote_status(self, repository_id: int) -> Optional[RemoteRepositoryStatusModel]:
        """Fetch remote repository status record for a given repository."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM remote_repository_status WHERE repository_id = ?",
                (repository_id,),
            )
            row = cursor.fetchone()
            if row:
                d = dict(row)
                return RemoteRepositoryStatusModel(
                    id=d["id"],
                    repository_id=d["repository_id"],
                    local_branch=d["local_branch"],
                    remote_branch=d["remote_branch"],
                    ahead_count=d["ahead_count"],
                    behind_count=d["behind_count"],
                    last_fetch_at=d.get("last_fetch_at"),
                    last_push_at=d.get("last_push_at"),
                    sync_status=d.get("sync_status", "unknown"),
                )
        return None

    def save_remote_status(
        self,
        repository_id: int,
        local_branch: str,
        remote_branch: str,
        ahead_count: int,
        behind_count: int,
        sync_status: str,
        last_fetch_at: Optional[str] = None,
        last_push_at: Optional[str] = None,
    ) -> RemoteRepositoryStatusModel:
        """Upsert remote repository status."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO remote_repository_status (
                    repository_id, local_branch, remote_branch,
                    ahead_count, behind_count, sync_status,
                    last_fetch_at, last_push_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id) DO UPDATE SET
                    local_branch=excluded.local_branch,
                    remote_branch=excluded.remote_branch,
                    ahead_count=excluded.ahead_count,
                    behind_count=excluded.behind_count,
                    sync_status=excluded.sync_status,
                    last_fetch_at=COALESCE(excluded.last_fetch_at, remote_repository_status.last_fetch_at),
                    last_push_at=COALESCE(excluded.last_push_at, remote_repository_status.last_push_at)
                """,
                (
                    repository_id,
                    local_branch,
                    remote_branch,
                    ahead_count,
                    behind_count,
                    sync_status,
                    last_fetch_at,
                    last_push_at,
                ),
            )
            status_id = cursor.lastrowid

        return RemoteRepositoryStatusModel(
            id=status_id,
            repository_id=repository_id,
            local_branch=local_branch,
            remote_branch=remote_branch,
            ahead_count=ahead_count,
            behind_count=behind_count,
            last_fetch_at=last_fetch_at,
            last_push_at=last_push_at,
            sync_status=sync_status,
        )

    def record_sync_operation(
        self,
        repository_id: int,
        operation_type: str,
        branch: str,
        status: str,
        commit_hash: Optional[str] = None,
        error_summary: Optional[str] = None,
    ) -> GitHubSyncHistoryModel:
        """Record a GitHub sync event (fetch or push)."""
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO github_sync_history (
                    repository_id, operation_type, branch, status,
                    commit_hash, started_at, completed_at, error_summary
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    repository_id,
                    operation_type,
                    branch,
                    status,
                    commit_hash,
                    now,
                    now,
                    error_summary,
                ),
            )
            rec_id = cursor.lastrowid

        return GitHubSyncHistoryModel(
            id=rec_id,
            repository_id=repository_id,
            operation_type=operation_type,
            branch=branch,
            status=status,
            commit_hash=commit_hash,
            started_at=now,
            completed_at=now,
            error_summary=error_summary,
        )

    def list_sync_history(
        self, repository_id: int, limit: int = 20
    ) -> List[GitHubSyncHistoryModel]:
        """Fetch sync history for a repository."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM github_sync_history
                WHERE repository_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (repository_id, limit),
            )
            rows = cursor.fetchall()
            return [
                GitHubSyncHistoryModel(
                    id=r["id"],
                    repository_id=r["repository_id"],
                    operation_type=r["operation_type"],
                    branch=r["branch"],
                    status=r["status"],
                    commit_hash=r["commit_hash"],
                    started_at=r["started_at"],
                    completed_at=r["completed_at"],
                    error_summary=r["error_summary"],
                )
                for r in rows
            ]

