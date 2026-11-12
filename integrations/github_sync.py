"""
GitHub Synchronization Engine for AutoGit AI (Phase 4).
Executes controlled remote fetching and pushing with strict permission enforcement,
secret validation, conflict verification, and audit trail logging.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from core.git_manager import GitManager
from core.permission_manager import PermissionDeniedError, PermissionManager
from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import GitHubSyncHistoryModel, RemoteRepositoryStatusModel
from database.sync_repository import SyncRepository
from integrations.conflict_manager import ConflictManager
from integrations.remote_status import RemoteStatusInspector
from utils.logger import logger
from utils.security import safe_subprocess_run
from validation.secret_scanner import SecretScanner


class GitHubSyncEngine:
    """Manages controlled fetch and push operations against authorized remote repositories."""

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        permission_mgr: Optional[PermissionManager] = None,
        sync_repo: Optional[SyncRepository] = None,
        status_inspector: Optional[RemoteStatusInspector] = None,
        conflict_mgr: Optional[ConflictManager] = None,
        secret_scanner: Optional[SecretScanner] = None,
    ):
        self.db = database or default_db
        self.permission_mgr = permission_mgr or PermissionManager(self.db)
        self.sync_repo = sync_repo or SyncRepository(self.db)
        self.status_inspector = status_inspector or RemoteStatusInspector(self.db, self.sync_repo)
        self.conflict_mgr = conflict_mgr or ConflictManager()
        self.secret_scanner = secret_scanner or SecretScanner()

    def fetch_repository(
        self, repository_id: int, remote_name: str = "origin"
    ) -> Dict[str, Any]:
        """
        Execute controlled git fetch from remote without modifying local working tree.
        Updates remote repository tracking status in SQLite.
        """
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        repo_path = Path(repo.repository_path).resolve()
        git_mgr = GitManager(repo_path)
        current_branch = git_mgr.get_current_branch() or "main"

        # Check if remote exists
        remotes = git_mgr.get_remotes()
        matched_remote = next((r["name"] for r in remotes if r["name"] == remote_name), None)
        if not matched_remote and remotes:
            matched_remote = remotes[0]["name"]

        if not matched_remote:
            err = f"No remote repository configured for '{repo.repository_name}'."
            self.sync_repo.record_sync_operation(
                repository_id=repository_id,
                operation_type="fetch",
                branch=current_branch,
                status="failed",
                error_summary=err,
            )
            return {"success": False, "error": err, "sync_status": "no_remote"}

        logger.info(f"Fetching from remote '{matched_remote}' for repo {repository_id} ({repo.repository_name})")

        # Execute safe fetch
        exit_code, stdout, stderr = safe_subprocess_run(
            ["git", "fetch", matched_remote],
            cwd=repo_path,
            timeout=30.0,
        )

        now = get_utc_now_iso()
        if exit_code != 0:
            err = stderr.strip() or stdout.strip() or "git fetch failed"
            logger.error(f"Fetch failed for repo {repository_id}: {err}")
            self.sync_repo.record_sync_operation(
                repository_id=repository_id,
                operation_type="fetch",
                branch=current_branch,
                status="failed",
                error_summary=err,
            )
            return {"success": False, "error": err}

        # Refresh remote tracking status
        status = self.status_inspector.get_remote_status(repository_id, refresh=True)
        self.sync_repo.record_sync_operation(
            repository_id=repository_id,
            operation_type="fetch",
            branch=current_branch,
            status="success",
        )

        return {
            "success": True,
            "operation": "fetch",
            "branch": current_branch,
            "remote": matched_remote,
            "ahead_count": status.ahead_count,
            "behind_count": status.behind_count,
            "sync_status": status.sync_status,
            "last_fetch_at": now,
        }

    def push_repository(
        self,
        repository_id: int,
        branch: Optional[str] = None,
        remote_name: str = "origin",
    ) -> Dict[str, Any]:
        """
        Execute controlled git push to remote.
        Strictly enforces:
        1. remote_push permission must be enabled.
        2. No force-pushing.
        3. No pushing if merge conflict exists.
        4. Secret validation before push.
        """
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        # 1. PERMISSION CHECK: Must have explicit remote_push permission
        if not self.permission_mgr.verify_permission(repository_id, "remote_push"):
            logger.warning(f"Remote push DENIED: repo {repository_id} lacks 'remote_push' permission.")
            raise PermissionDeniedError(
                f"Repository '{repo.repository_name}' is not authorized for remote push. "
                "Please enable the 'Remote Push' permission first."
            )

        repo_path = Path(repo.repository_path).resolve()
        git_mgr = GitManager(repo_path)
        target_branch = branch or git_mgr.get_current_branch() or "main"

        # Check if remote exists
        remotes = git_mgr.get_remotes()
        matched_remote = next((r["name"] for r in remotes if r["name"] == remote_name), None)
        if not matched_remote and remotes:
            matched_remote = remotes[0]["name"]

        if not matched_remote:
            err = f"No remote configured for '{repo.repository_name}'."
            return {"success": False, "error": err}

        remote_tracking_branch = f"{matched_remote}/{target_branch}"

        # 2. Conflict & Divergence Check
        conflict_result = self.conflict_mgr.check_conflicts(
            repo_path=repo_path,
            local_branch=target_branch,
            remote_branch=remote_tracking_branch,
        )
        if conflict_result.get("has_conflict"):
            err = f"Push blocked: Remote conflict detected on branch '{target_branch}'."
            self.sync_repo.record_sync_operation(
                repository_id=repository_id,
                operation_type="push",
                branch=target_branch,
                status="conflict",
                error_summary=err,
            )
            return {
                "success": False,
                "conflict": True,
                "error": err,
                "conflicting_files": conflict_result.get("conflicting_files", []),
            }

        # 3. Commits Ahead Check
        status = self.status_inspector.get_remote_status(repository_id, refresh=True)
        if status.ahead_count == 0 and status.sync_status == "synced":
            return {
                "success": True,
                "pushed": False,
                "message": "Already up to date. No local commits ahead to push.",
                "sync_status": "synced",
            }

        # 4. Secret Scanner Check on Ahead Commits
        ahead_commits_output = safe_subprocess_run(
            ["git", "diff", f"{remote_tracking_branch}..{target_branch}"],
            cwd=repo_path,
            timeout=10.0,
        )[1]
        if ahead_commits_output:
            findings = self.secret_scanner.scan_text(ahead_commits_output, file_path="ahead_commits")
            if findings:
                err = f"Push aborted: {len(findings)} potential secret(s) detected in commits being pushed."
                logger.error(err)
                self.sync_repo.record_sync_operation(
                    repository_id=repository_id,
                    operation_type="push",
                    branch=target_branch,
                    status="failed",
                    error_summary=err,
                )
                return {"success": False, "error": err, "secrets_detected": True}

        # 5. Execute git push (NEVER use force)
        logger.info(f"Pushing {status.ahead_count} commit(s) on branch '{target_branch}' to '{matched_remote}'")
        exit_code, stdout, stderr = safe_subprocess_run(
            ["git", "push", matched_remote, target_branch],
            cwd=repo_path,
            timeout=60.0,
        )

        now = get_utc_now_iso()
        if exit_code != 0:
            err = stderr.strip() or stdout.strip() or "git push failed"
            logger.error(f"Push failed for repo {repository_id}: {err}")
            self.sync_repo.record_sync_operation(
                repository_id=repository_id,
                operation_type="push",
                branch=target_branch,
                status="failed",
                error_summary=err,
            )
            return {"success": False, "error": err}

        # Retrieve latest pushed commit hash
        latest_commit = git_mgr.get_latest_commit()
        commit_hash = latest_commit.get("hexsha") if latest_commit else None

        # Update status
        self.sync_repo.save_remote_status(
            repository_id=repository_id,
            local_branch=target_branch,
            remote_branch=remote_tracking_branch,
            ahead_count=0,
            behind_count=status.behind_count,
            sync_status="synced" if status.behind_count == 0 else "behind",
            last_push_at=now,
        )

        self.sync_repo.record_sync_operation(
            repository_id=repository_id,
            operation_type="push",
            branch=target_branch,
            status="success",
            commit_hash=commit_hash,
        )

        logger.info(f"Push completed successfully for '{repo.repository_name}' on '{target_branch}'.")
        return {
            "success": True,
            "operation": "push",
            "branch": target_branch,
            "remote": matched_remote,
            "commit_hash": commit_hash,
            "last_push_at": now,
            "sync_status": "synced" if status.behind_count == 0 else "behind",
        }

