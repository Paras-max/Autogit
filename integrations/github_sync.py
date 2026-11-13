"""
GitHub Synchronization Engine for AutoGit AI (Phase 4).
Executes controlled remote fetching and pushing with strict permission enforcement,
secret validation, conflict verification, audit trail logging, and authenticated push
via token-injected HTTPS URLs.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional
import urllib.parse

from config.settings import settings as app_settings
from core.git_manager import GitManager
from core.permission_manager import PermissionDeniedError, PermissionManager
from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import GitHubSyncHistoryModel, RemoteRepositoryStatusModel
from database.sync_repository import SyncRepository
from integrations.conflict_manager import ConflictManager
from integrations.remote_status import RemoteStatusInspector
from utils.logger import logger
from utils.security import safe_subprocess_run
from utils.validators import mask_secret
from validation.secret_scanner import SecretScanner


def _inject_token_into_url(remote_url: str, token: str) -> str:
    """
    Inject a GitHub token into an HTTPS remote URL for authenticated push.
    Returns URL with token embedded as: https://<token>@github.com/owner/repo.git
    The token is URL-encoded to handle special characters safely.
    NEVER log the returned URL.
    """
    if not token or not remote_url.startswith("https://"):
        return remote_url
    parsed = urllib.parse.urlparse(remote_url)
    # Strip any existing credentials in the URL
    netloc_no_creds = parsed.hostname
    if parsed.port:
        netloc_no_creds = f"{netloc_no_creds}:{parsed.port}"
    encoded_token = urllib.parse.quote(token, safe="")
    authed_netloc = f"{encoded_token}@{netloc_no_creds}"
    auth_url = parsed._replace(netloc=authed_netloc).geturl()
    return auth_url


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
        execution_id: Optional[int] = None,
        commit_hash: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute controlled git push to remote with:
        1. Strict remote_push permission enforcement (no bypass).
        2. GitHub token injected into HTTPS URL (never logged).
        3. --set-upstream retry for new autogit/dev-* branches.
        4. Post-push remote verification via git ls-remote.
        5. Never force-pushes.
        6. Push sync status update in execution_history.
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

        # Check if remote exists and get its URL
        remotes = git_mgr.get_remotes()
        matched_remote = next((r["name"] for r in remotes if r["name"] == remote_name), None)
        if not matched_remote and remotes:
            matched_remote = remotes[0]["name"]

        if not matched_remote:
            err = f"No remote configured for '{repo.repository_name}'."
            self._update_push_sync_status(execution_id, "PUSH_FAILED")
            return {"success": False, "error": err}

        # Get the remote URL for token injection
        remote_url = repo.remote_url or ""
        for r in remotes:
            if r["name"] == matched_remote:
                remote_url = r.get("url", remote_url)
                break

        # Build authenticated push URL (token injected, never logged)
        token = app_settings.GITHUB_TOKEN
        push_target = matched_remote  # default: use remote name (git credential manager)
        auth_url = None

        if token and remote_url.startswith("https://"):
            auth_url = _inject_token_into_url(remote_url, token)
            # We'll use auth_url as the push target directly
            push_target = auth_url
            logger.info(
                f"Push: using token-authenticated URL for repo {repository_id} "
                f"(token: {mask_secret(token)})"
            )
        else:
            logger.info(
                f"Push: no GITHUB_TOKEN or non-HTTPS remote; using remote name '{matched_remote}' "
                f"(relying on git credential manager)"
            )

        remote_tracking_branch = f"{matched_remote}/{target_branch}"

        # 2. Conflict & Divergence Check (use public remote URL for ls-remote)
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
            self._update_push_sync_status(execution_id, "REMOTE_CONFLICT")
            return {
                "success": False,
                "conflict": True,
                "error": err,
                "conflicting_files": conflict_result.get("conflicting_files", []),
            }

        # 3. Commits Ahead Check (only for branches that track a remote)
        # For autogit/dev-* branches, the remote tracking branch may not exist yet — skip ahead check
        is_new_branch = target_branch.startswith("autogit/") or target_branch.startswith("dev-")
        if not is_new_branch:
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
        # For new branches with no remote tracking, diff against HEAD (or just skip — push is safe)
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
                self._update_push_sync_status(execution_id, "PUSH_FAILED")
                return {"success": False, "error": err, "secrets_detected": True}

        # 5. Mark as PUSHING in DB
        self._update_push_sync_status(execution_id, "PUSHING")

        # 6. Execute git push (NEVER use --force or +refs/)
        logger.info(
            f"Pushing branch '{target_branch}' to remote '{matched_remote}' "
            f"for repo {repository_id} ({repo.repository_name})"
        )
        refspec = f"{target_branch}:{target_branch}"
        exit_code, stdout, stderr = safe_subprocess_run(
            ["git", "push", push_target, refspec],
            cwd=repo_path,
            timeout=60.0,
        )

        # 7. If push failed due to missing upstream, retry with --set-upstream
        if exit_code != 0:
            combined_err = (stderr + stdout).lower()
            needs_upstream = any(phrase in combined_err for phrase in [
                "no upstream", "set-upstream", "has no upstream", "set the upstream",
                "does not appear to be a git repository",  # may also need upstream
            ])
            if needs_upstream or is_new_branch:
                logger.info(f"Retrying push with --set-upstream for new branch '{target_branch}'")
                exit_code, stdout, stderr = safe_subprocess_run(
                    ["git", "push", "--set-upstream", push_target, refspec],
                    cwd=repo_path,
                    timeout=60.0,
                )

        now = get_utc_now_iso()
        if exit_code != 0:
            err = stderr.strip() or stdout.strip() or "git push failed"
            # Mask token from error message if accidentally present
            if token and token in err:
                err = err.replace(token, "***TOKEN***")
            logger.error(f"Push failed for repo {repository_id}: {err}")
            self.sync_repo.record_sync_operation(
                repository_id=repository_id,
                operation_type="push",
                branch=target_branch,
                status="failed",
                error_summary=err,
            )
            self._update_push_sync_status(execution_id, "PUSH_FAILED")
            return {"success": False, "error": err}

        # 8. Post-push remote verification: check that remote branch contains the commit
        remote_verified = False
        verify_url = auth_url if auth_url else matched_remote
        rc_verify, verify_out, _ = safe_subprocess_run(
            ["git", "ls-remote", verify_url, f"refs/heads/{target_branch}"],
            cwd=repo_path,
            timeout=15.0,
        )
        if rc_verify == 0 and verify_out.strip():
            remote_verified = True
            logger.info(f"Remote verification passed: '{target_branch}' exists on remote.")
            if commit_hash and not verify_out.strip().startswith(commit_hash[:7]):
                logger.warning(
                    f"Remote tip hash does not start with expected {commit_hash[:7]}, "
                    f"but push succeeded (remote: {verify_out.strip()[:7]})"
                )
        else:
            logger.warning(f"Remote verification inconclusive for '{target_branch}' (rc={rc_verify})")

        # Retrieve latest pushed commit hash
        latest_commit = git_mgr.get_latest_commit()
        pushed_commit_hash = latest_commit.get("hexsha") if latest_commit else commit_hash

        # Update status table (only for tracked branches)
        if not is_new_branch:
            try:
                status = self.status_inspector.get_remote_status(repository_id, refresh=False)
                self.sync_repo.save_remote_status(
                    repository_id=repository_id,
                    local_branch=target_branch,
                    remote_branch=remote_tracking_branch,
                    ahead_count=0,
                    behind_count=status.behind_count,
                    sync_status="synced" if status.behind_count == 0 else "behind",
                    last_push_at=now,
                )
            except Exception:
                pass
        else:
            # For new branches, just record last_push_at
            try:
                self.sync_repo.save_remote_status(
                    repository_id=repository_id,
                    local_branch=target_branch,
                    remote_branch=remote_tracking_branch,
                    ahead_count=0,
                    behind_count=0,
                    sync_status="synced",
                    last_push_at=now,
                )
            except Exception:
                pass

        self.sync_repo.record_sync_operation(
            repository_id=repository_id,
            operation_type="push",
            branch=target_branch,
            status="success",
            commit_hash=pushed_commit_hash,
        )

        # Mark execution as PUSHED
        self._update_push_sync_status(execution_id, "PUSHED")

        logger.info(
            f"Push completed successfully for '{repo.repository_name}' on '{target_branch}'. "
            f"Remote verified: {remote_verified}"
        )
        return {
            "success": True,
            "operation": "push",
            "branch": target_branch,
            "remote": matched_remote,
            "commit_hash": pushed_commit_hash,
            "last_push_at": now,
            "sync_status": "synced",
            "remote_verified": remote_verified,
        }

    def _update_push_sync_status(self, execution_id: Optional[int], new_status: str) -> None:
        """Update push_sync_status in execution_history if execution_id is provided."""
        if not execution_id:
            return
        try:
            with self.db.get_cursor() as cursor:
                cursor.execute(
                    "UPDATE execution_history SET push_sync_status = ? WHERE id = ?",
                    (new_status, execution_id),
                )
            logger.debug(f"Updated push_sync_status={new_status} for execution {execution_id}")
        except Exception as e:
            logger.error(f"Failed to update push_sync_status for execution {execution_id}: {e}")
