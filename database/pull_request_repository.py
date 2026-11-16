"""
Pull Request repository for Phase 4 Step 4 database operations.
Manages persistent records for GitHub Pull Requests in SQLite with:
- Strict unique constraint on (repository_id, pr_number).
- Idempotent upsert functionality preserving history.
- Lifecycle tracking: OPEN, CLOSED, MERGED, DRAFT, REVIEW_PENDING, CHANGES_REQUESTED.
- Atomic transaction safety.
"""

from typing import List, Optional
from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import PullRequestModel
from utils.logger import logger


class PullRequestRepository:
    """Repository handling SQLite persistence for GitHub Pull Requests."""

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def _row_to_model(self, row: dict) -> PullRequestModel:
        return PullRequestModel(
            id=row["id"],
            repository_id=row["repository_id"],
            pr_number=row["pr_number"],
            title=row["title"],
            source_branch=row["source_branch"],
            target_branch=row["target_branch"],
            state=row["state"],
            html_url=row["html_url"],
            is_merged=bool(row["is_merged"]),
            created_at=row["created_at"] or "",
            updated_at=row["updated_at"] or "",
            merged_at=row.get("merged_at"),
            body=row.get("body"),
            diff_url=row.get("diff_url"),
            github_pr_id=row.get("github_pr_id"),
            head_commit_sha=row.get("head_commit_sha"),
            base_commit_sha=row.get("base_commit_sha"),
            is_draft=bool(row.get("is_draft", 0)),
            last_synced_at=row.get("last_synced_at"),
            last_sync_error=row.get("last_sync_error"),
        )

    def create_or_update_pr(self, model: PullRequestModel) -> PullRequestModel:
        """
        Idempotently create or update a Pull Request record.
        Uses SQLite ON CONFLICT(repository_id, pr_number) DO UPDATE.
        """
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO pull_requests (
                    repository_id,
                    pr_number,
                    title,
                    source_branch,
                    target_branch,
                    state,
                    html_url,
                    is_merged,
                    created_at,
                    updated_at,
                    merged_at,
                    body,
                    diff_url,
                    github_pr_id,
                    head_commit_sha,
                    base_commit_sha,
                    is_draft,
                    last_synced_at,
                    last_sync_error
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(repository_id, pr_number) DO UPDATE SET
                    title=excluded.title,
                    source_branch=excluded.source_branch,
                    target_branch=excluded.target_branch,
                    state=excluded.state,
                    html_url=excluded.html_url,
                    is_merged=excluded.is_merged,
                    updated_at=excluded.updated_at,
                    merged_at=excluded.merged_at,
                    body=excluded.body,
                    diff_url=excluded.diff_url,
                    github_pr_id=excluded.github_pr_id,
                    head_commit_sha=excluded.head_commit_sha,
                    base_commit_sha=excluded.base_commit_sha,
                    is_draft=excluded.is_draft,
                    last_synced_at=excluded.last_synced_at,
                    last_sync_error=excluded.last_sync_error
                """,
                (
                    model.repository_id,
                    model.pr_number,
                    model.title,
                    model.source_branch,
                    model.target_branch,
                    model.state,
                    model.html_url,
                    int(model.is_merged),
                    model.created_at or now,
                    model.updated_at or now,
                    model.merged_at,
                    model.body,
                    model.diff_url,
                    model.github_pr_id,
                    model.head_commit_sha,
                    model.base_commit_sha,
                    int(model.is_draft),
                    model.last_synced_at or now,
                    model.last_sync_error,
                ),
            )
            if not model.id:
                model.id = cursor.lastrowid
        return model

    def get_pr_by_number(self, repository_id: int, pr_number: int) -> Optional[PullRequestModel]:
        """Fetch a PR record by repository ID and PR number."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM pull_requests WHERE repository_id = ? AND pr_number = ?",
                (repository_id, pr_number),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_model(dict(row))
        return None

    def get_pr_by_id(self, pr_id: int) -> Optional[PullRequestModel]:
        """Fetch a PR record by its internal primary key ID."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM pull_requests WHERE id = ?",
                (pr_id,),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_model(dict(row))
        return None

    def list_prs_for_repository(
        self, repository_id: int, state: Optional[str] = None
    ) -> List[PullRequestModel]:
        """List all PR records for a repository, optionally filtered by state."""
        with self.db.get_cursor() as cursor:
            if state:
                cursor.execute(
                    "SELECT * FROM pull_requests WHERE repository_id = ? AND LOWER(state) = LOWER(?) ORDER BY pr_number DESC",
                    (repository_id, state),
                )
            else:
                cursor.execute(
                    "SELECT * FROM pull_requests WHERE repository_id = ? ORDER BY pr_number DESC",
                    (repository_id,),
                )
            rows = cursor.fetchall()
            return [self._row_to_model(dict(r)) for r in rows]

    def find_open_pr(
        self, repository_id: int, source_branch: str, target_branch: str
    ) -> Optional[PullRequestModel]:
        """Find an existing OPEN or DRAFT PR for the given repository and branch pair."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM pull_requests
                WHERE repository_id = ?
                  AND source_branch = ?
                  AND target_branch = ?
                  AND LOWER(state) IN ('open', 'draft', 'review_pending', 'changes_requested')
                ORDER BY pr_number DESC
                LIMIT 1
                """,
                (repository_id, source_branch, target_branch),
            )
            row = cursor.fetchone()
            if row:
                return self._row_to_model(dict(row))
        return None

    def update_lifecycle(
        self,
        repository_id: int,
        pr_number: int,
        state: str,
        is_merged: bool,
        is_draft: bool = False,
        merged_at: Optional[str] = None,
        last_sync_error: Optional[str] = None,
    ) -> Optional[PullRequestModel]:
        """Update PR lifecycle state, merged status, draft flag, and sync timestamp."""
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE pull_requests
                SET state = ?,
                    is_merged = ?,
                    is_draft = ?,
                    merged_at = COALESCE(?, merged_at),
                    last_synced_at = ?,
                    last_sync_error = ?,
                    updated_at = ?
                WHERE repository_id = ? AND pr_number = ?
                """,
                (
                    state,
                    int(is_merged),
                    int(is_draft),
                    merged_at,
                    now,
                    last_sync_error,
                    now,
                    repository_id,
                    pr_number,
                ),
            )
        return self.get_pr_by_number(repository_id, pr_number)
