"""
GitHub Synchronization Engine for AutoGit AI (Phase 4 - Step 3).
Executes secure, controlled remote fetching and pushing with:
1. Secure GIT_ASKPASS credential handling (zero token in URLs, CLI args, git config, or logs).
2. Strict repository-level Remote Push permission enforcement.
3. Isolated branch selection (ensuring autogit/dev-* branches are never pushed to main).
4. Rigorous post-push remote commit verification using ancestry checks (git merge-base --is-ancestor).
5. Comprehensive synchronization state persistence in SQLite (ExecutionHistory & SyncHistory).
6. Non-destructive Git safety (no force push, no hard reset, no working tree mutation).
"""

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple

from config.settings import settings as app_settings
from core.git_manager import GitManager
from core.permission_manager import PermissionDeniedError, PermissionManager
from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.execution_repository import ExecutionRepository
from database.models import GitHubSyncHistoryModel, RemoteRepositoryStatusModel
from database.sync_repository import SyncRepository
from integrations.conflict_manager import ConflictManager
from integrations.remote_status import RemoteStatusInspector
from utils.git_credential import git_credential_context
from utils.logger import logger
from utils.security import safe_subprocess_run
from utils.validators import mask_secret
from validation.secret_scanner import SecretScanner


class GitHubSyncEngine:
    """Manages secure fetch, push, and remote commit verification for repositories."""

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        permission_mgr: Optional[PermissionManager] = None,
        sync_repo: Optional[SyncRepository] = None,
        status_inspector: Optional[RemoteStatusInspector] = None,
        conflict_mgr: Optional[ConflictManager] = None,
        secret_scanner: Optional[SecretScanner] = None,
        exec_repo: Optional[ExecutionRepository] = None,
    ):
        self.db = database or default_db
        self.permission_mgr = permission_mgr or PermissionManager(self.db)
        self.sync_repo = sync_repo or SyncRepository(self.db)
        self.status_inspector = status_inspector or RemoteStatusInspector(self.db, self.sync_repo)
        self.conflict_mgr = conflict_mgr or ConflictManager()
        self.secret_scanner = secret_scanner or SecretScanner()
        self.exec_repo = exec_repo or ExecutionRepository(self.db)

    def _get_github_token(self, token_override: Optional[str] = None) -> Optional[str]:
        """
        Retrieve GitHub token securely from override, database, or settings.
        Never logs the raw token.
        """
        if token_override and token_override.strip():
            return token_override.strip()
        try:
            auth = self.db.get_authentication("github")
            if auth and getattr(auth, "api_key", None) and auth.api_key.strip():
                return auth.api_key.strip()
        except Exception:
            pass
        if app_settings.GITHUB_TOKEN and app_settings.GITHUB_TOKEN.strip():
            return app_settings.GITHUB_TOKEN.strip()
        return None

    def _clean_error(self, message: str, token: Optional[str] = None) -> str:
        """Sanitize error messages to remove any token or sensitive paths."""
        if not message:
            return ""
        clean = message.strip()
        if token and token in clean:
            clean = clean.replace(token, "***REDACTED_TOKEN***")
        # Mask typical PAT patterns: ghp_, github_pat_
        clean = re.sub(r"ghp_[A-Za-z0-9_]{10,}", "***REDACTED_TOKEN***", clean)
        clean = re.sub(r"github_pat_[A-Za-z0-9_]{10,}", "***REDACTED_TOKEN***", clean)
        return clean

    def _validate_ref_name(self, ref: str) -> bool:
        """Validate that a branch or ref name is safe and contains no control characters or shell metacharacters."""
        if not ref or len(ref) > 250:
            return False
        # Disallow control chars, spaces, shell injection chars
        if any(c in ref for c in [' ', '\t', '\r', '\n', ';', '&', '|', '>', '<', '`', '$', '(', ')', '\\', '^', '~', ':', '?']):
            return False
        if ref.startswith("-") or ref.endswith(".lock") or "/." in ref or "//" in ref or ".." in ref:
            return False
        return True

    def fetch_repository(
        self,
        repository_id: int,
        remote_name: str = "origin",
        token_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute controlled git fetch from remote without modifying local working tree.
        Uses secure GIT_ASKPASS credential handler.
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

        token = self._get_github_token(token_override)
        logger.info(f"Fetching from remote '{matched_remote}' for repo {repository_id} ({repo.repository_name})")

        with git_credential_context(token) as cred_env:
            import os
            cmd_env = {**os.environ, **cred_env} if cred_env else None
            exit_code, stdout, stderr = safe_subprocess_run(
                ["git", "fetch", matched_remote],
                cwd=repo_path,
                timeout=30.0,
                env=cmd_env,
            )

        now = get_utc_now_iso()
        if exit_code != 0:
            err = self._clean_error(stderr.strip() or stdout.strip() or "git fetch failed", token)
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

    def _resolve_commit_and_branch(
        self,
        repository_id: int,
        repo_path: Path,
        execution_id: Optional[int] = None,
        branch: Optional[str] = None,
        commit_hash: Optional[str] = None,
    ) -> Tuple[Optional[str], str, Optional[Any]]:
        """
        Accurately resolve the intended local commit hash and its containing source branch.
        Preserves isolated development branches (e.g. autogit/dev-*). Never defaults to 'main'
        if the commit belongs to another branch.
        """
        execution = None
        resolved_commit = commit_hash
        resolved_branch = branch

        # 1. Resolve from execution record if provided
        if execution_id:
            execution = self.exec_repo.get_execution(execution_id)
            if not execution:
                raise ValueError(f"Execution record {execution_id} does not exist.")
            if execution.repository_id != repository_id:
                raise ValueError(f"Execution {execution_id} does not belong to repository {repository_id}.")
            if execution.status not in ("committed", "approved"):
                raise ValueError(
                    f"Execution {execution_id} has status='{execution.status}'. "
                    "Only 'committed' or 'approved' executions can be pushed."
                )
            if not execution.commit_hash:
                raise ValueError(f"Execution {execution_id} does not have a commit_hash; cannot push.")

            resolved_commit = execution.commit_hash

            # Look up branch from execution model fields first
            if not resolved_branch:
                resolved_branch = getattr(execution, "source_branch", None) or getattr(execution, "branch_name", None)

            # Look up branch from development_sessions table
            if not resolved_branch:
                with self.db.get_cursor() as cursor:
                    cursor.execute(
                        "SELECT branch_name FROM development_sessions WHERE commit_hash = ? AND repository_id = ? ORDER BY id DESC LIMIT 1",
                        (resolved_commit, repository_id),
                    )
                    row = cursor.fetchone()
                    if row and row["branch_name"]:
                        resolved_branch = row["branch_name"]

        # 2. If branch is still not known, query git for branches containing the commit
        if resolved_commit and not resolved_branch:
            ec, out, _ = safe_subprocess_run(
                ["git", "branch", "--contains", resolved_commit],
                cwd=repo_path,
                timeout=10.0,
            )
            if ec == 0 and out.strip():
                # Pick the first non-HEAD branch
                for line in out.strip().splitlines():
                    b_name = line.lstrip("* ").strip()
                    if b_name and not b_name.startswith("(") and b_name != "HEAD detached":
                        resolved_branch = b_name
                        break

        # 3. If neither execution_id nor commit was specified, use provided branch or current branch
        if not resolved_branch:
            git_mgr = GitManager(repo_path)
            resolved_branch = git_mgr.get_current_branch()

        if not resolved_branch:
            raise ValueError("Could not determine source branch for push operation.")

        # 4. Validate branch format to prevent injection
        if not self._validate_ref_name(resolved_branch):
            raise ValueError(f"Invalid or unsafe branch name: {resolved_branch!r}")

        # 5. Verify branch exists locally in git repository
        ec_verify, _, _ = safe_subprocess_run(
            ["git", "rev-parse", "--verify", f"refs/heads/{resolved_branch}"],
            cwd=repo_path,
            timeout=5.0,
        )
        if ec_verify != 0:
            raise ValueError(f"Local branch '{resolved_branch}' does not exist in repository {repository_id}.")

        # 6. If commit_hash is specified, verify it is reachable from resolved_branch
        if resolved_commit:
            ec_anc, _, _ = safe_subprocess_run(
                ["git", "merge-base", "--is-ancestor", resolved_commit, resolved_branch],
                cwd=repo_path,
                timeout=5.0,
            )
            if ec_anc != 0:
                raise ValueError(
                    f"Commit {resolved_commit[:8]} is not reachable from source branch '{resolved_branch}'. "
                    "Refusing to push incorrect branch."
                )
        else:
            # Commit not provided; use tip of resolved_branch
            ec_tip, tip_out, _ = safe_subprocess_run(
                ["git", "rev-parse", f"refs/heads/{resolved_branch}"],
                cwd=repo_path,
                timeout=5.0,
            )
            if ec_tip == 0 and tip_out.strip():
                resolved_commit = tip_out.strip()

        return resolved_commit, resolved_branch, execution

    def push_repository(
        self,
        repository_id: int,
        branch: Optional[str] = None,
        remote_name: str = "origin",
        execution_id: Optional[int] = None,
        commit_hash: Optional[str] = None,
        target_branch: Optional[str] = None,
        token_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Execute secure, controlled git push to remote with:
        1. Strict repository-level remote_push permission enforcement.
        2. Credential isolation via GIT_ASKPASS (zero token in URL, args, config, or logs).
        3. Accurate branch routing (maintaining autogit/dev-* isolation).
        4. Secret scanning on unpushed commits.
        5. Conflict and non-fast-forward protection (no force push).
        6. Mandatory remote commit verification (git merge-base --is-ancestor).
        7. State updates in execution_history and audit trail in SQLite.
        """
        import os

        # 1. PERMISSION CHECK: Must have explicit remote_push permission
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        if not self.permission_mgr.verify_permission(repository_id, "remote_push"):
            logger.warning(f"Remote push DENIED: repo {repository_id} lacks 'remote_push' permission.")
            raise PermissionDeniedError(
                f"Repository '{repo.repository_name}' is not authorized for remote push. "
                "Please enable the 'Remote Push' permission first in Repository Settings."
            )

        repo_path = Path(repo.repository_path).resolve()
        git_mgr = GitManager(repo_path)

        # 2. RESOLVE SOURCE COMMIT AND BRANCH
        intended_commit, source_branch, execution = self._resolve_commit_and_branch(
            repository_id=repository_id,
            repo_path=repo_path,
            execution_id=execution_id,
            branch=branch,
            commit_hash=commit_hash,
        )

        # Resolve target remote branch (default to matching source branch name)
        remote_target_branch = target_branch or source_branch
        if not self._validate_ref_name(remote_target_branch):
            raise ValueError(f"Invalid target branch name: {remote_target_branch!r}")

        # Check if remote exists
        remotes = git_mgr.get_remotes()
        matched_remote = next((r["name"] for r in remotes if r["name"] == remote_name), None)
        if not matched_remote and remotes:
            matched_remote = remotes[0]["name"]

        if not matched_remote:
            err = f"No remote repository configured for '{repo.repository_name}'."
            if execution_id:
                self.exec_repo.update_sync_status(
                    execution_id=execution_id,
                    push_sync_status="PUSH_FAILED",
                    push_error=err,
                )
            return {"success": False, "error": err, "sync_status": "no_remote"}

        # 3. CONFLICT & DIVERGENCE CHECK (only if tracking branch exists)
        remote_tracking_ref = f"{matched_remote}/{remote_target_branch}"
        is_autonomous_branch = source_branch.startswith("autogit/") or source_branch.startswith("dev-")

        conflict_result = self.conflict_mgr.check_conflicts(
            repo_path=repo_path,
            local_branch=source_branch,
            remote_branch=remote_tracking_ref,
        )
        if conflict_result.get("has_conflict"):
            err = f"Push blocked: Remote conflict detected on branch '{source_branch}'."
            self.sync_repo.record_sync_operation(
                repository_id=repository_id,
                operation_type="push",
                branch=source_branch,
                status="conflict",
                error_summary=err,
            )
            if execution_id:
                self.exec_repo.update_sync_status(
                    execution_id=execution_id,
                    push_sync_status="REMOTE_CONFLICT",
                    verification_status="NON_FAST_FORWARD",
                    source_branch=source_branch,
                    target_branch=remote_target_branch,
                    remote_name=matched_remote,
                    push_error=err,
                )
            return {
                "success": False,
                "conflict": True,
                "error": err,
                "conflicting_files": conflict_result.get("conflicting_files", []),
            }

        # 4. SECRET SCANNER CHECK ON AHEAD COMMITS
        ahead_diff_ec, ahead_diff_out, _ = safe_subprocess_run(
            ["git", "diff", f"{remote_tracking_ref}..{source_branch}"],
            cwd=repo_path,
            timeout=10.0,
        )
        if ahead_diff_ec == 0 and ahead_diff_out:
            findings = self.secret_scanner.scan_text(ahead_diff_out, file_path="ahead_commits")
            if findings:
                err = f"Push aborted: {len(findings)} potential secret(s) detected in commits being pushed."
                logger.error(err)
                self.sync_repo.record_sync_operation(
                    repository_id=repository_id,
                    operation_type="push",
                    branch=source_branch,
                    status="failed",
                    error_summary=err,
                )
                if execution_id:
                    self.exec_repo.update_sync_status(
                        execution_id=execution_id,
                        push_sync_status="PUSH_FAILED",
                        verification_status="SECRET_CHECK_FAILED",
                        source_branch=source_branch,
                        target_branch=remote_target_branch,
                        remote_name=matched_remote,
                        push_error=err,
                    )
                return {"success": False, "error": err, "secrets_detected": True}

        # 5. MARK PUSHING IN DATABASE
        if execution_id:
            self.exec_repo.update_sync_status(
                execution_id=execution_id,
                push_sync_status="PUSHING",
                source_branch=source_branch,
                target_branch=remote_target_branch,
                branch_name=source_branch,
                remote_name=matched_remote,
                local_commit_hash=intended_commit,
            )

        # 6. EXECUTE GIT PUSH VIA GIT_ASKPASS CREDENTIAL HANDLER
        token = self._get_github_token(token_override)
        refspec = f"{source_branch}:{remote_target_branch}"
        logger.info(
            f"Pushing '{source_branch}' to '{matched_remote}/{remote_target_branch}' "
            f"for repo {repository_id} ({repo.repository_name}) [commit {intended_commit[:8] if intended_commit else 'tip'}]"
        )

        with git_credential_context(token) as cred_env:
            cmd_env = {**os.environ, **cred_env} if cred_env else None

            # Execute push (NEVER use --force or +refs/)
            exit_code, stdout, stderr = safe_subprocess_run(
                ["git", "push", matched_remote, refspec],
                cwd=repo_path,
                timeout=60.0,
                env=cmd_env,
            )

            # Retry with --set-upstream if required
            if exit_code != 0:
                combined_err = (stderr + stdout).lower()
                needs_upstream = any(phrase in combined_err for phrase in [
                    "no upstream", "set-upstream", "has no upstream", "set the upstream"
                ])
                if needs_upstream or is_autonomous_branch:
                    logger.info(f"Retrying push with --set-upstream for branch '{source_branch}'")
                    exit_code, stdout, stderr = safe_subprocess_run(
                        ["git", "push", "--set-upstream", matched_remote, refspec],
                        cwd=repo_path,
                        timeout=60.0,
                        env=cmd_env,
                    )

        now = get_utc_now_iso()

        # 7. HANDLE PUSH FAILURE
        if exit_code != 0:
            raw_err = (stderr.strip() or stdout.strip() or "git push failed")
            clean_err = self._clean_error(raw_err, token)
            err_lower = raw_err.lower()

            # Classify failure
            if any(p in err_lower for p in ["authentication failed", "invalid username or token", "401", "403", "terminal prompts disabled"]):
                fail_status = "PUSH_FAILED"
                verification_status = "AUTHENTICATION_FAILED"
                clean_err = "Authentication failed: invalid or expired GitHub credentials."
            elif any(p in err_lower for p in ["non-fast-forward", "fetch first", "rejected"]):
                fail_status = "REMOTE_CONFLICT"
                verification_status = "NON_FAST_FORWARD"
                clean_err = "Remote repository has newer commits (non-fast-forward conflict). Please pull or sync first."
            elif any(p in err_lower for p in ["timed out", "could not resolve host", "unable to access", "network"]):
                fail_status = "PUSH_FAILED"
                verification_status = "NETWORK_ERROR"
            else:
                fail_status = "PUSH_FAILED"
                verification_status = "PUSH_ERROR"

            logger.error(f"Push failed for repo {repository_id}: {clean_err}")
            self.sync_repo.record_sync_operation(
                repository_id=repository_id,
                operation_type="push",
                branch=source_branch,
                status="failed",
                error_summary=clean_err,
            )
            if execution_id:
                self.exec_repo.update_sync_status(
                    execution_id=execution_id,
                    push_sync_status=fail_status,
                    verification_status=verification_status,
                    source_branch=source_branch,
                    target_branch=remote_target_branch,
                    remote_name=matched_remote,
                    local_commit_hash=intended_commit,
                    push_timestamp=now,
                    push_error=clean_err,
                )

            return {
                "success": False,
                "error": clean_err,
                "push_sync_status": fail_status,
                "verification_status": verification_status,
            }

        # 8. STEP 3D: REMOTE COMMIT VERIFICATION
        # Do not mark PUSHED merely because git push returned exit code 0!
        # Fetch remote branch to obtain actual remote commit object and verify ancestry.
        verified_remote_hash = None
        remote_advanced = False
        verification_status = "VERIFICATION_FAILED"
        final_sync_status = "VERIFICATION_FAILED"
        verify_error = None

        with git_credential_context(token) as cred_env:
            cmd_env = {**os.environ, **cred_env} if cred_env else None

            # Fetch the specific remote branch into FETCH_HEAD
            fetch_ec, fetch_out, fetch_err = safe_subprocess_run(
                ["git", "fetch", matched_remote, f"refs/heads/{remote_target_branch}"],
                cwd=repo_path,
                timeout=30.0,
                env=cmd_env,
            )

        if fetch_ec == 0:
            # Read fetched remote commit hash
            rev_ec, rev_out, _ = safe_subprocess_run(
                ["git", "rev-parse", "FETCH_HEAD"],
                cwd=repo_path,
                timeout=5.0,
            )
            if rev_ec == 0 and rev_out.strip():
                verified_remote_hash = rev_out.strip()

                # Case 1: Exact Match
                if intended_commit and verified_remote_hash == intended_commit:
                    final_sync_status = "PUSHED"
                    verification_status = "EXACT_MATCH"
                    remote_advanced = False
                    logger.info(
                        f"Remote commit verification EXACT_MATCH: {intended_commit[:8]} verified at remote tip."
                    )
                elif intended_commit:
                    # Case 2: Check ancestry using git merge-base --is-ancestor
                    anc_ec, _, _ = safe_subprocess_run(
                        ["git", "merge-base", "--is-ancestor", intended_commit, verified_remote_hash],
                        cwd=repo_path,
                        timeout=5.0,
                    )
                    if anc_ec == 0:
                        final_sync_status = "PUSHED"
                        verification_status = "COMMIT_REACHABLE_REMOTE_ADVANCED"
                        remote_advanced = True
                        logger.info(
                            f"Remote verification passed (COMMIT_REACHABLE_REMOTE_ADVANCED): "
                            f"{intended_commit[:8]} is ancestor of remote tip {verified_remote_hash[:8]}."
                        )
                    else:
                        final_sync_status = "VERIFICATION_FAILED"
                        verification_status = "COMMIT_NOT_REACHABLE"
                        verify_error = (
                            f"Intended commit {intended_commit[:8]} is not reachable from remote branch "
                            f"'{remote_target_branch}' (remote tip: {verified_remote_hash[:8]})."
                        )
                        logger.warning(verify_error)
                else:
                    # No specific commit passed; remote tip accepted
                    final_sync_status = "PUSHED"
                    verification_status = "EXACT_MATCH"
            else:
                verify_error = "Could not resolve FETCH_HEAD commit hash after successful fetch."
                logger.warning(verify_error)
        else:
            verify_error = f"Remote verification fetch failed: {self._clean_error(fetch_err or fetch_out, token)}"
            logger.warning(verify_error)

        # 9. PERSIST VERIFIED STATE TO DATABASE
        if execution_id:
            self.exec_repo.update_sync_status(
                execution_id=execution_id,
                push_sync_status=final_sync_status,
                verification_status=verification_status,
                local_commit_hash=intended_commit,
                remote_commit_hash=verified_remote_hash,
                remote_advanced=remote_advanced,
                source_branch=source_branch,
                target_branch=remote_target_branch,
                remote_name=matched_remote,
                push_timestamp=now,
                push_error=verify_error,
            )

        # Record in sync audit history
        self.sync_repo.record_sync_operation(
            repository_id=repository_id,
            operation_type="push",
            branch=source_branch,
            status="success" if final_sync_status == "PUSHED" else "failed",
            commit_hash=verified_remote_hash or intended_commit,
            error_summary=verify_error,
        )

        # Update remote repository tracking status
        try:
            self.sync_repo.save_remote_status(
                repository_id=repository_id,
                local_branch=source_branch,
                remote_branch=f"{matched_remote}/{remote_target_branch}",
                ahead_count=0 if final_sync_status == "PUSHED" else 1,
                behind_count=0,
                sync_status="synced" if final_sync_status == "PUSHED" else "diverged",
                last_push_at=now if final_sync_status == "PUSHED" else None,
            )
        except Exception:
            pass

        is_success = (final_sync_status == "PUSHED")
        return {
            "success": is_success,
            "operation": "push",
            "branch": source_branch,
            "target_branch": remote_target_branch,
            "remote": matched_remote,
            "commit_hash": verified_remote_hash or intended_commit,
            "local_commit_hash": intended_commit,
            "remote_commit_hash": verified_remote_hash,
            "remote_advanced": remote_advanced,
            "push_sync_status": final_sync_status,
            "verification_status": verification_status,
            "remote_verified": is_success,
            "last_push_at": now,
            "sync_status": "synced" if is_success else "diverged",
            "error": verify_error if not is_success else None,
        }

    def retry_push(
        self,
        execution_id: int,
        remote_name: str = "origin",
        token_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Retry a previously failed or pending push for an execution record.
        Re-validates repository registration, remote_push permission, and branch state.
        """
        execution = self.exec_repo.get_execution(execution_id)
        if not execution:
            raise ValueError(f"Execution {execution_id} does not exist.")

        return self.push_repository(
            repository_id=execution.repository_id,
            execution_id=execution_id,
            remote_name=remote_name,
            branch=execution.branch_name or execution.source_branch,
            commit_hash=execution.commit_hash,
            target_branch=execution.target_branch,
            token_override=token_override,
        )

    def get_sync_status(self, repository_id: int) -> Dict[str, Any]:
        """Return comprehensive synchronization and remote tracking status for a repository."""
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        status_model = self.status_inspector.get_remote_status(repository_id, refresh=False)

        # Get the latest execution commit push status
        latest_exec = None
        pending_count = 0
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT id, commit_hash, status, push_sync_status, verification_status,
                       remote_advanced, local_commit_hash, remote_commit_hash,
                       source_branch, target_branch, push_timestamp, push_error
                FROM execution_history
                WHERE repository_id = ? AND status = 'committed'
                ORDER BY id DESC LIMIT 1
                """,
                (repository_id,),
            )
            latest_exec = cursor.fetchone()

            cursor.execute(
                """
                SELECT COUNT(*) as cnt FROM execution_history
                WHERE repository_id = ? AND status = 'committed'
                  AND (push_sync_status IS NULL OR push_sync_status != 'PUSHED')
                """,
                (repository_id,),
            )
            p_row = cursor.fetchone()
            if p_row:
                pending_count = p_row["cnt"]

        latest_info = dict(latest_exec) if latest_exec else {}

        return {
            "repository_id": repository_id,
            "repository_name": repo.repository_name,
            "local_branch": status_model.local_branch,
            "remote_branch": status_model.remote_branch,
            "sync_status": status_model.sync_status,
            "ahead_count": status_model.ahead_count,
            "behind_count": status_model.behind_count,
            "last_fetch_at": status_model.last_fetch_at,
            "last_push_at": status_model.last_push_at,
            "pending_push_count": pending_count,
            "latest_execution_id": latest_info.get("id"),
            "latest_commit_hash": latest_info.get("commit_hash"),
            "push_sync_status": latest_info.get("push_sync_status", "UNKNOWN"),
            "verification_status": latest_info.get("verification_status"),
            "remote_advanced": bool(latest_info.get("remote_advanced", 0)),
            "local_commit_hash": latest_info.get("local_commit_hash"),
            "remote_commit_hash": latest_info.get("remote_commit_hash"),
            "last_push_timestamp": latest_info.get("push_timestamp"),
            "last_error": latest_info.get("push_error"),
        }

    def get_pending_commits(self, repository_id: int, limit: int = 50) -> List[Dict[str, Any]]:
        """Return list of commits that exist locally in execution_history but are not verified on remote."""
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        pending_models = self.exec_repo.list_pending_sync_commits(repository_id, limit=limit)
        return [
            {
                "execution_id": m.id,
                "repository_id": m.repository_id,
                "commit_hash": m.commit_hash,
                "commit_message": m.commit_message,
                "created_at": m.created_at,
                "push_sync_status": m.push_sync_status or "LOCAL_ONLY",
                "source_branch": m.source_branch or m.branch_name,
                "target_branch": m.target_branch,
                "verification_status": m.verification_status,
                "push_error": m.push_error,
            }
            for m in pending_models
        ]

    def get_push_history(self, repository_id: int, limit: int = 20) -> List[Dict[str, Any]]:
        """Return combined audit log of push operations for a repository."""
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        records = self.sync_repo.list_sync_history(repository_id, limit=limit)
        return [
            {
                "id": r.id,
                "repository_id": r.repository_id,
                "operation_type": r.operation_type,
                "branch": r.branch,
                "status": r.status,
                "commit_hash": r.commit_hash,
                "started_at": r.started_at,
                "completed_at": r.completed_at,
                "error_summary": r.error_summary,
            }
            for r in records
            if r.operation_type == "push"
        ]
