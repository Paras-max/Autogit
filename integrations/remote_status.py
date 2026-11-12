"""
Remote Repository Status Inspector for AutoGit AI (Phase 4).
Inspects local vs remote Git configuration, calculates ahead/behind counts,
determines synchronization status, and updates remote_repository_status in SQLite.
"""

from datetime import datetime, timezone
import os
from pathlib import Path
from typing import Any, Dict, Optional

from core.git_manager import GitManager
from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import RemoteRepositoryStatusModel
from database.sync_repository import SyncRepository
from utils.logger import logger
from utils.security import safe_subprocess_run


class RemoteStatusInspector:
    """Inspects Git remote configuration, tracking branches, ahead/behind counts, and sync status."""

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        sync_repo: Optional[SyncRepository] = None,
    ):
        self.db = database or default_db
        self.sync_repo = sync_repo or SyncRepository(self.db)

    def get_remote_status(
        self, repository_id: int, refresh: bool = True
    ) -> RemoteRepositoryStatusModel:
        """
        Get remote tracking status for a repository.
        If refresh=True, inspects the local Git repository directly and updates SQLite.
        """
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        if not refresh:
            cached = self.sync_repo.get_remote_status(repository_id)
            if cached:
                return cached

        repo_path = Path(repo.repository_path).resolve()
        git_mgr = GitManager(repo_path)
        local_branch = git_mgr.get_current_branch() or "main"

        # Check if remote exists
        remotes = git_mgr.get_remotes()
        remote_name = "origin" if any(r["name"] == "origin" for r in remotes) else (remotes[0]["name"] if remotes else None)

        if not remote_name:
            # No remote configured
            return self.sync_repo.save_remote_status(
                repository_id=repository_id,
                local_branch=local_branch,
                remote_branch="",
                ahead_count=0,
                behind_count=0,
                sync_status="no_remote",
            )

        remote_branch = f"{remote_name}/{local_branch}"

        # Check if remote tracking ref exists
        exit_code, _, _ = safe_subprocess_run(
            ["git", "rev-parse", "--verify", remote_branch], cwd=repo_path, timeout=5.0
        )
        has_remote_ref = (exit_code == 0)

        ahead_count = 0
        behind_count = 0
        sync_status = "unknown"

        if not has_remote_ref:
            # Remote branch ref not fetched or does not exist on remote yet
            # Count local commits on branch
            exit_code_cnt, stdout_cnt, _ = safe_subprocess_run(
                ["git", "rev-list", "--count", local_branch], cwd=repo_path, timeout=5.0
            )
            ahead_count = int(stdout_cnt.strip()) if exit_code_cnt == 0 and stdout_cnt.strip().isdigit() else 0
            behind_count = 0
            sync_status = "ahead" if ahead_count > 0 else "synced"
        else:
            # Ahead count: local commits not yet on remote
            exit_code_ahead, stdout_ahead, _ = safe_subprocess_run(
                ["git", "rev-list", "--count", f"{remote_branch}..{local_branch}"],
                cwd=repo_path,
                timeout=5.0,
            )
            if exit_code_ahead == 0 and stdout_ahead.strip().isdigit():
                ahead_count = int(stdout_ahead.strip())

            # Behind count: remote commits not yet in local branch
            exit_code_behind, stdout_behind, _ = safe_subprocess_run(
                ["git", "rev-list", "--count", f"{local_branch}..{remote_branch}"],
                cwd=repo_path,
                timeout=5.0,
            )
            if exit_code_behind == 0 and stdout_behind.strip().isdigit():
                behind_count = int(stdout_behind.strip())

            # Determine sync status
            if ahead_count == 0 and behind_count == 0:
                sync_status = "synced"
            elif ahead_count > 0 and behind_count == 0:
                sync_status = "ahead"
            elif ahead_count == 0 and behind_count > 0:
                sync_status = "behind"
            else:
                sync_status = "diverged"

        # Check FETCH_HEAD timestamp if available
        fetch_head = repo_path / ".git" / "FETCH_HEAD"
        last_fetch = None
        if fetch_head.exists():
            try:
                mtime = os.path.getmtime(fetch_head)
                last_fetch = datetime.fromtimestamp(mtime, tz=timezone.utc).isoformat()
            except Exception:
                pass

        cached_status = self.sync_repo.get_remote_status(repository_id)
        last_push = cached_status.last_push_at if cached_status else None

        updated = self.sync_repo.save_remote_status(
            repository_id=repository_id,
            local_branch=local_branch,
            remote_branch=remote_branch,
            ahead_count=ahead_count,
            behind_count=behind_count,
            sync_status=sync_status,
            last_fetch_at=last_fetch,
            last_push_at=last_push,
        )
        return updated

