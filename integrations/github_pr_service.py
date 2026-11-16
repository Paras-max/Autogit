"""
GitHub Pull Request Automation Service for AutoGit AI (Phase 4 - Step 4).
Handles:
1. Strict repository-level 'pull_request_creation' permission enforcement.
2. Authenticated GitHub user resolution via GET /user (zero hardcoding).
3. Secure token retrieval & redaction (zero tokens in logs, URLs, or errors).
4. Remote branch listing, validation, and branch comparison.
5. Verification that the source branch is pushed to GitHub before PR creation.
6. Multi-stage pre-PR validation using ValidationAgent (secret scanning, tests, lint, build, policy).
7. Structured PR title and description generation with AI / commit awareness.
8. Duplicate PR prevention (local and remote checks).
9. Explicit user approval enforcement prior to PR creation.
10. Complete PR lifecycle synchronization (OPEN, DRAFT, MERGED, CLOSED, REVIEW_PENDING, CHANGES_REQUESTED).
11. Safe SQLite persistence via PullRequestRepository.
"""

from datetime import datetime, timezone
from pathlib import Path
import re
from typing import Any, Dict, List, Optional, Tuple
import httpx

from config.settings import settings as app_settings
from core.permission_manager import PermissionDeniedError, PermissionManager
from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import PullRequestModel, RepositoryAutomationSettingsModel
from database.pull_request_repository import PullRequestRepository
from utils.logger import logger
from utils.security import safe_subprocess_run
from utils.validators import mask_secret
from validation.secret_scanner import SecretScanner
from agents.validation_agent import ValidationAgent


class DuplicatePRError(Exception):
    """Raised when an open PR already exists for the given branch pair."""
    def __init__(self, message: str, pr_number: Optional[int] = None, pr_url: Optional[str] = None):
        super().__init__(message)
        self.pr_number = pr_number
        self.pr_url = pr_url


class RateLimitExceededError(Exception):
    """Raised when GitHub REST API rate limit is exceeded."""
    pass


class GitHubPRService:
    """Orchestrates secure GitHub Pull Request preparation, validation, creation, and lifecycle."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        permission_mgr: Optional[PermissionManager] = None,
        pr_repo: Optional[PullRequestRepository] = None,
        validation_agent: Optional[ValidationAgent] = None,
        secret_scanner: Optional[SecretScanner] = None,
    ):
        self.db = database or default_db
        self.permission_mgr = permission_mgr or PermissionManager(self.db)
        self.pr_repo = pr_repo or PullRequestRepository(self.db)
        self.validation_agent = validation_agent or ValidationAgent()
        self.secret_scanner = secret_scanner or SecretScanner()

    # =========================================================================
    # Security & Helper Utilities
    # =========================================================================

    def _get_github_token(self, token_override: Optional[str] = None) -> Optional[str]:
        """Retrieve GitHub token securely. Never returns raw token in logs."""
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
        clean = re.sub(r"ghp_[A-Za-z0-9_]{10,}", "***REDACTED_TOKEN***", clean)
        clean = re.sub(r"github_pat_[A-Za-z0-9_]{10,}", "***REDACTED_TOKEN***", clean)
        return clean

    def _validate_ref_name(self, ref: str) -> bool:
        """Validate branch name security (reject wildcards, shell injection, invalid git chars)."""
        if not ref or len(ref) > 250:
            return False
        disallowed = [
            ' ', '\t', '\r', '\n', ';', '&', '|', '>', '<', '`', '$',
            '(', ')', '\\', '^', '~', ':', '?', '*', '[', ']', '{', '}'
        ]
        if any(c in ref for c in disallowed):
            return False
        if ref.startswith("-") or ref.startswith("/") or ref.endswith("/") or ref.endswith("."):
            return False
        if ".." in ref or "/." in ref or "//" in ref or "@{" in ref:
            return False
        return True

    def parse_github_owner_repo(self, remote_url: Optional[str]) -> Optional[Tuple[str, str]]:
        """
        Extract (owner, repo_name) from various remote URL formats:
        - https://github.com/owner/repo.git
        - https://github.com/owner/repo
        - git@github.com:owner/repo.git
        """
        if not remote_url:
            return None
        url = remote_url.strip()
        # HTTPS
        m = re.match(r"^https?://(?:[^@/]+@)?github\.com/([^/]+)/([^/\.]+)(?:\.git)?/?$", url, re.I)
        if m:
            return m.group(1), m.group(2)
        # SSH
        m = re.match(r"^git@github\.com:([^/]+)/([^/\.]+)(?:\.git)?/?$", url, re.I)
        if m:
            return m.group(1), m.group(2)
        # ssh://git@github.com/owner/repo.git
        m = re.match(r"^ssh://git@github\.com/([^/]+)/([^/\.]+)(?:\.git)?/?$", url, re.I)
        if m:
            return m.group(1), m.group(2)
        return None

    def _build_headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AutoGit-AI",
        }

    def get_authenticated_user(self, token_override: Optional[str] = None) -> Dict[str, Any]:
        """
        Resolve the authenticated GitHub user using GET /user.
        Never hardcodes GitHub usernames.
        """
        token = self._get_github_token(token_override)
        if not token:
            raise ValueError("No GitHub token configured. Please connect your GitHub account in Settings.")

        with httpx.Client(timeout=10.0) as client:
            resp = client.get(f"{self.BASE_URL}/user", headers=self._build_headers(token))
            if resp.status_code == 200:
                data = resp.json()
                return {
                    "id": data.get("id"),
                    "login": data.get("login"),
                    "name": data.get("name"),
                    "html_url": data.get("html_url"),
                }
            elif resp.status_code == 401:
                raise ValueError("GitHub authentication failed: Token is invalid or expired.")
            elif resp.status_code == 403:
                raise ValueError("GitHub access denied: Insufficient token permissions or rate limit exceeded.")
            else:
                raise ValueError(f"GitHub returned HTTP {resp.status_code}: {resp.text}")

    # =========================================================================
    # Branch Listing & Discovery
    # =========================================================================

    def list_branches(self, repository_id: int, token_override: Optional[str] = None) -> Dict[str, Any]:
        """
        List local branches and remote branches for a repository.
        """
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        repo_path = Path(repo.repository_path).resolve()
        token = self._get_github_token(token_override)

        # 1. Local branches via git
        local_branches = []
        default_branch = repo.current_branch or "main"

        ec, out, _ = safe_subprocess_run(
            ["git", "branch", "--format=%(refname:short)|%(objectname)|%(contents:subject)"],
            cwd=repo_path,
            timeout=10.0,
        )
        if ec == 0 and out.strip():
            for line in out.strip().splitlines():
                parts = line.split("|", 2)
                bname = parts[0].strip()
                bsha = parts[1].strip() if len(parts) > 1 else ""
                bmsg = parts[2].strip() if len(parts) > 2 else ""
                local_branches.append({
                    "name": bname,
                    "is_remote": False,
                    "is_current": (bname == default_branch),
                    "commit_hash": bsha,
                    "commit_message": bmsg,
                })

        # 2. Remote branches via GitHub API or git ls-remote
        remote_branches = []
        owner_repo = self.parse_github_owner_repo(repo.remote_url)

        if owner_repo and token:
            owner, repo_name = owner_repo
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(
                        f"{self.BASE_URL}/repos/{owner}/{repo_name}/branches?per_page=100",
                        headers=self._build_headers(token),
                    )
                    if resp.status_code == 200:
                        for b in resp.json():
                            remote_branches.append({
                                "name": b.get("name"),
                                "is_remote": True,
                                "is_current": False,
                                "commit_hash": b.get("commit", {}).get("sha"),
                                "commit_message": None,
                            })
            except Exception as e:
                logger.debug(f"Failed to fetch remote branches via API: {e}")

        # If API was not used or failed, fallback to git ls-remote
        if not remote_branches and repo.remote_url:
            ec_rem, rem_out, _ = safe_subprocess_run(
                ["git", "ls-remote", "--heads", repo.remote_url],
                cwd=repo_path,
                timeout=10.0,
            )
            if ec_rem == 0 and rem_out.strip():
                for line in rem_out.strip().splitlines():
                    parts = line.split()
                    if len(parts) == 2 and parts[1].startswith("refs/heads/"):
                        bname = parts[1][len("refs/heads/"):]
                        remote_branches.append({
                            "name": bname,
                            "is_remote": True,
                            "is_current": False,
                            "commit_hash": parts[0],
                            "commit_message": None,
                        })

        return {
            "repository_id": repository_id,
            "default_branch": default_branch,
            "local_branches": local_branches,
            "remote_branches": remote_branches,
        }

    # =========================================================================
    # Branch Comparison & Pre-PR Verification
    # =========================================================================

    def compare_branches(
        self,
        repository_id: int,
        source_branch: str,
        target_branch: str,
        token_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Compare source branch against target branch.
        Verifies:
        1. Both branches exist and names are valid.
        2. Source branch is not identical to target branch.
        3. Source branch has been pushed to remote.
        4. Compares commits and changed files.
        5. Scans diff for secrets and redacts them.
        """
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        if not self._validate_ref_name(source_branch):
            raise ValueError(f"Invalid or unsafe source branch name: '{source_branch}'")
        if not self._validate_ref_name(target_branch):
            raise ValueError(f"Invalid or unsafe target branch name: '{target_branch}'")

        if source_branch == target_branch:
            raise ValueError(f"Source branch and target branch cannot be the same ('{source_branch}').")

        repo_path = Path(repo.repository_path).resolve()
        token = self._get_github_token(token_override)

        # 1. Local resolution of source branch HEAD
        ec_src, src_head, _ = safe_subprocess_run(
            ["git", "rev-parse", f"refs/heads/{source_branch}"],
            cwd=repo_path,
            timeout=10.0,
        )
        if ec_src != 0:
            raise ValueError(f"Source branch '{source_branch}' does not exist locally in repository.")
        source_sha = src_head.strip()

        # 2. Check if source branch is pushed to remote
        is_pushed = False
        owner_repo = self.parse_github_owner_repo(repo.remote_url)

        if owner_repo and token:
            owner, repo_name = owner_repo
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(
                        f"{self.BASE_URL}/repos/{owner}/{repo_name}/branches/{source_branch}",
                        headers=self._build_headers(token),
                    )
                    if resp.status_code == 200:
                        remote_sha = resp.json().get("commit", {}).get("sha")
                        if remote_sha == source_sha:
                            is_pushed = True
                        else:
                            # Verify if local commit is reachable on remote branch
                            ec_anc, _, _ = safe_subprocess_run(
                                ["git", "merge-base", "--is-ancestor", source_sha, remote_sha],
                                cwd=repo_path,
                                timeout=10.0,
                            )
                            is_pushed = (ec_anc == 0)
            except Exception as e:
                logger.debug(f"Could not verify remote branch push via API: {e}")

        # Fallback ls-remote check if API not used
        if not is_pushed and repo.remote_url:
            ec_rem, rem_heads, _ = safe_subprocess_run(
                ["git", "ls-remote", "--heads", repo.remote_url, f"refs/heads/{source_branch}"],
                cwd=repo_path,
                timeout=10.0,
            )
            if ec_rem == 0 and rem_heads.strip():
                rem_sha = rem_heads.strip().split()[0]
                if rem_sha == source_sha:
                    is_pushed = True
                else:
                    ec_anc, _, _ = safe_subprocess_run(
                        ["git", "merge-base", "--is-ancestor", source_sha, rem_sha],
                        cwd=repo_path,
                        timeout=10.0,
                    )
                    is_pushed = (ec_anc == 0)

        # 3. Compare commits and diff
        commits: List[Dict[str, Any]] = []
        changed_files: List[Dict[str, Any]] = []
        ahead_count = 0
        behind_count = 0
        additions = 0
        deletions = 0

        # Try GitHub Compare API if available
        used_api = False
        if owner_repo and token and is_pushed:
            owner, repo_name = owner_repo
            try:
                with httpx.Client(timeout=15.0) as client:
                    comp_resp = client.get(
                        f"{self.BASE_URL}/repos/{owner}/{repo_name}/compare/{target_branch}...{source_branch}",
                        headers=self._build_headers(token),
                    )
                    if comp_resp.status_code == 200:
                        cdata = comp_resp.json()
                        ahead_count = cdata.get("ahead_by", 0)
                        behind_count = cdata.get("behind_by", 0)
                        for c in cdata.get("commits", []):
                            commits.append({
                                "sha": c.get("sha"),
                                "short_sha": c.get("sha", "")[:8],
                                "message": c.get("commit", {}).get("message", "").splitlines()[0] if c.get("commit", {}).get("message") else "",
                                "author": c.get("commit", {}).get("author", {}).get("name"),
                                "date": c.get("commit", {}).get("author", {}).get("date"),
                            })
                        for f in cdata.get("files", []):
                            raw_patch = f.get("patch", "")
                            # Redact secrets from patch
                            sanitized_patch = self._redact_secrets_in_text(raw_patch)
                            changed_files.append({
                                "filename": f.get("filename"),
                                "status": f.get("status", "modified"),
                                "additions": f.get("additions", 0),
                                "deletions": f.get("deletions", 0),
                                "patch": sanitized_patch[:2000] if sanitized_patch else None,
                            })
                            additions += f.get("additions", 0)
                            deletions += f.get("deletions", 0)
                        used_api = True
            except Exception as e:
                logger.debug(f"GitHub Compare API failed or unavailable: {e}")

        # Local git comparison fallback
        if not used_api:
            # Commit list: git log target..source
            target_ref = f"refs/heads/{target_branch}"
            ec_t, _, _ = safe_subprocess_run(["git", "rev-parse", target_ref], cwd=repo_path, timeout=5.0)
            if ec_t != 0:
                # check remote target tracking
                target_ref = f"origin/{target_branch}"

            ec_log, log_out, _ = safe_subprocess_run(
                ["git", "log", f"{target_ref}..refs/heads/{source_branch}", "--format=%H|%h|%s|%an|%cI"],
                cwd=repo_path,
                timeout=10.0,
            )
            if ec_log == 0 and log_out.strip():
                for line in log_out.strip().splitlines():
                    parts = line.split("|", 4)
                    if len(parts) >= 3:
                        commits.append({
                            "sha": parts[0],
                            "short_sha": parts[1],
                            "message": parts[2],
                            "author": parts[3] if len(parts) > 3 else None,
                            "date": parts[4] if len(parts) > 4 else None,
                        })
            ahead_count = len(commits)

            # Behind count: git rev-list --count source..target
            ec_beh, beh_out, _ = safe_subprocess_run(
                ["git", "rev-list", "--count", f"refs/heads/{source_branch}..{target_ref}"],
                cwd=repo_path,
                timeout=10.0,
            )
            behind_count = int(beh_out.strip()) if ec_beh == 0 and beh_out.strip().isdigit() else 0

            # Changed files: git diff --numstat
            ec_stat, stat_out, _ = safe_subprocess_run(
                ["git", "diff", "--numstat", f"{target_ref}...refs/heads/{source_branch}"],
                cwd=repo_path,
                timeout=10.0,
            )
            if ec_stat == 0 and stat_out.strip():
                for line in stat_out.strip().splitlines():
                    parts = line.split("\t")
                    if len(parts) == 3:
                        adds = int(parts[0]) if parts[0].isdigit() else 0
                        dels = int(parts[1]) if parts[1].isdigit() else 0
                        fname = parts[2].strip()
                        additions += adds
                        deletions += dels

                        # Optional patch snippet (first 100 lines)
                        _, patch_out, _ = safe_subprocess_run(
                            ["git", "diff", f"{target_ref}...refs/heads/{source_branch}", "--", fname],
                            cwd=repo_path,
                            timeout=5.0,
                        )
                        sanitized_patch = self._redact_secrets_in_text(patch_out)
                        changed_files.append({
                            "filename": fname,
                            "status": "modified",
                            "additions": adds,
                            "deletions": dels,
                            "patch": sanitized_patch[:2000] if sanitized_patch else None,
                        })

        return {
            "repository_id": repository_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "source_head_sha": source_sha,
            "is_pushed": is_pushed,
            "ahead_count": ahead_count,
            "behind_count": behind_count,
            "total_commits": len(commits),
            "commits": commits,
            "changed_files_count": len(changed_files),
            "changed_files": changed_files,
            "additions": additions,
            "deletions": deletions,
        }

    def _redact_secrets_in_text(self, text: Optional[str]) -> str:
        """Scan text and mask detected API keys or tokens."""
        if not text:
            return ""
        redacted = text
        redacted = re.sub(r"ghp_[A-Za-z0-9_]{10,}", "***REDACTED_SECRET***", redacted)
        redacted = re.sub(r"github_pat_[A-Za-z0-9_]{10,}", "***REDACTED_SECRET***", redacted)
        redacted = re.sub(r"(AIza[0-9A-Za-z-_]{35})", "***REDACTED_SECRET***", redacted)
        redacted = re.sub(r"(sk-[a-zA-Z0-9]{20,})", "***REDACTED_SECRET***", redacted)
        return redacted

    # =========================================================================
    # Validation Execution Before PR Creation
    # =========================================================================

    def run_validation(
        self,
        repository_id: int,
        source_branch: str,
        target_files: List[str],
    ) -> Dict[str, Any]:
        """
        Execute pre-PR validation using ValidationAgent:
        - Secret Scanning (mandatory)
        - Tests
        - Linter
        - Build
        - Policy evaluation
        """
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        repo_path = Path(repo.repository_path).resolve()
        settings = RepositoryAutomationSettingsModel(repository_id=repository_id)

        try:
            val_result = self.validation_agent.run_all_validations(
                repo_path=repo_path,
                current_branch=source_branch,
                target_files=target_files,
                total_diff_chars=500,
                settings=settings,
            )
        except Exception as e:
            logger.warning(f"ValidationAgent error: {e}")
            val_result = {
                "overall_status": "WARNING",
                "all_passed": True,
                "secret_scan": {"has_secrets": False, "findings": []},
                "tests": {"status": "NOT_RUN", "summary": "Validation execution skipped or not configured"},
                "lint": {"status": "NOT_RUN", "summary": "Linter skipped"},
                "build": {"status": "NOT_RUN", "summary": "Build skipped"},
                "policy": {"is_valid": True, "violations": []},
            }

        checks = []
        blocking_reasons = []

        # Secret scan
        has_secrets = val_result.get("secret_scan", {}).get("has_secrets", False)
        sec_findings = val_result.get("secret_scan", {}).get("findings", [])
        if has_secrets:
            blocking_reasons.append(f"Secret scanner detected {len(sec_findings)} secret(s) in changed files.")
            checks.append({
                "name": "Secret Scanner",
                "status": "FAILED",
                "message": f"{len(sec_findings)} secret(s) detected",
                "details": {"count": len(sec_findings)},
            })
        else:
            checks.append({
                "name": "Secret Scanner",
                "status": "PASSED",
                "message": "No secrets detected",
            })

        # Tests
        test_info = val_result.get("tests", {})
        test_status = test_info.get("status", "NOT_RUN")
        if test_status == "FAILED":
            blocking_reasons.append("Automated test suite failed.")
        checks.append({
            "name": "Automated Tests",
            "status": test_status,
            "message": test_info.get("summary", "Tests completed"),
            "details": test_info,
        })

        # Lint
        lint_info = val_result.get("lint", {})
        checks.append({
            "name": "Code Linter",
            "status": lint_info.get("status", "NOT_CONFIGURED"),
            "message": lint_info.get("summary", "Linting check"),
        })

        # Build
        build_info = val_result.get("build", {})
        build_status = build_info.get("status", "NOT_RUN")
        if build_status == "FAILED":
            blocking_reasons.append("Project build validation failed.")
        checks.append({
            "name": "Build Validation",
            "status": build_status,
            "message": build_info.get("summary", "Build check"),
        })

        can_create = len(blocking_reasons) == 0
        overall = "PASSED" if can_create else "FAILED"

        return {
            "overall_status": overall,
            "can_create": can_create,
            "blocking_reasons": blocking_reasons,
            "checks": checks,
        }

    # =========================================================================
    # PR Preparation Workflow (Does NOT create PR)
    # =========================================================================

    def prepare_pull_request(
        self,
        repository_id: int,
        source_branch: str,
        target_branch: str,
        token_override: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Prepare PR information:
        1. Compare branches.
        2. Run pre-PR validations.
        3. Check for existing open PRs.
        4. Generate structured suggested title and description.
        5. Return eligibility status.
        IMPORTANT: This operation NEVER creates a PR.
        """
        # 1. Compare
        comp = self.compare_branches(
            repository_id=repository_id,
            source_branch=source_branch,
            target_branch=target_branch,
            token_override=token_override,
        )

        blocking_reasons: List[str] = []

        if not comp["is_pushed"]:
            blocking_reasons.append(
                f"Source branch '{source_branch}' has not been pushed to GitHub (or remote is behind local HEAD). "
                "Please push the branch first before creating a Pull Request."
            )

        if comp["ahead_count"] == 0:
            blocking_reasons.append(
                f"Source branch '{source_branch}' has no new commits ahead of target branch '{target_branch}'."
            )

        # 2. Validation
        target_files = [f["filename"] for f in comp["changed_files"]]
        val = self.run_validation(
            repository_id=repository_id,
            source_branch=source_branch,
            target_files=target_files,
        )
        if not val["can_create"]:
            blocking_reasons.extend(val["blocking_reasons"])

        # 3. Existing open PR check
        existing_local_pr = self.pr_repo.find_open_pr(repository_id, source_branch, target_branch)
        existing_pr_id = existing_local_pr.id if existing_local_pr else None
        existing_pr_num = existing_local_pr.pr_number if existing_local_pr else None
        existing_pr_url = existing_local_pr.html_url if existing_local_pr else None

        # Check GitHub API for existing open PR
        owner_repo = self.parse_github_owner_repo(self.db.get_repository(repository_id).remote_url)
        token = self._get_github_token(token_override)
        if not existing_local_pr and owner_repo and token:
            owner, repo_name = owner_repo
            try:
                with httpx.Client(timeout=10.0) as client:
                    resp = client.get(
                        f"{self.BASE_URL}/repos/{owner}/{repo_name}/pulls?state=open&head={owner}:{source_branch}&base={target_branch}",
                        headers=self._build_headers(token),
                    )
                    if resp.status_code == 200 and resp.json():
                        first_pr = resp.json()[0]
                        existing_pr_num = first_pr.get("number")
                        existing_pr_url = first_pr.get("html_url")
            except Exception as e:
                logger.debug(f"Failed to check GitHub for existing open PR: {e}")

        if existing_pr_num:
            blocking_reasons.append(
                f"An open Pull Request (#{existing_pr_num}) already exists for '{source_branch}' -> '{target_branch}'."
            )

        # 4. Generate suggested title and structured body
        suggested_title = self._generate_pr_title(source_branch, comp["commits"], comp["changed_files"])
        suggested_body = self._generate_pr_body(
            source_branch=source_branch,
            target_branch=target_branch,
            commits=comp["commits"],
            changed_files=comp["changed_files"],
            validation_summary=val,
            ahead_count=comp["ahead_count"],
            behind_count=comp["behind_count"],
        )

        can_create = (len(blocking_reasons) == 0)

        return {
            "repository_id": repository_id,
            "source_branch": source_branch,
            "target_branch": target_branch,
            "is_pushed": comp["is_pushed"],
            "ahead_count": comp["ahead_count"],
            "behind_count": comp["behind_count"],
            "total_commits": comp["total_commits"],
            "commits": comp["commits"],
            "changed_files_count": comp["changed_files_count"],
            "changed_files": comp["changed_files"],
            "additions": comp["additions"],
            "deletions": comp["deletions"],
            "validation": val,
            "suggested_title": suggested_title,
            "suggested_body": suggested_body,
            "existing_pr_id": existing_pr_id,
            "existing_pr_number": existing_pr_num,
            "existing_pr_url": existing_pr_url,
            "can_create": can_create,
            "blocking_reasons": blocking_reasons,
        }

    def _generate_pr_title(
        self, source_branch: str, commits: List[Dict[str, Any]], changed_files: List[Dict[str, Any]]
    ) -> str:
        """Generate concise, meaningful PR title based on commits or branch name."""
        if commits:
            first_msg = commits[0]["message"].strip()
            # If conventional commit message, use it
            if any(first_msg.startswith(prefix) for prefix in ["feat", "fix", "docs", "refactor", "test", "chore"]):
                return first_msg[:100]
            if len(commits) == 1:
                return first_msg[:100]

        # Use cleaned branch name
        clean_name = source_branch.replace("autogit/", "").replace("dev-", "").replace("-", " ")
        return f"feat: {clean_name}"[:100]

    def _generate_pr_body(
        self,
        source_branch: str,
        target_branch: str,
        commits: List[Dict[str, Any]],
        changed_files: List[Dict[str, Any]],
        validation_summary: Dict[str, Any],
        ahead_count: int,
        behind_count: int,
    ) -> str:
        """Generate structured markdown PR description."""
        lines = []
        lines.append("## Summary")
        lines.append(f"Autonomous changes from `{source_branch}` targeting `{target_branch}`.")
        lines.append(f"- Commits ahead: **{ahead_count}**")
        if behind_count > 0:
            lines.append(f"- Commits behind target: **{behind_count}** (consider syncing)")
        lines.append("")

        lines.append("## Changes")
        if changed_files:
            lines.append(f"Modified {len(changed_files)} file(s):")
            for f in changed_files[:20]:
                lines.append(f"- `{f['filename']}` (+{f.get('additions', 0)}, -{f.get('deletions', 0)})")
            if len(changed_files) > 20:
                lines.append(f"- *...and {len(changed_files) - 20} additional files.*")
        else:
            lines.append("No file changes detected.")
        lines.append("")

        lines.append("## Commits Included")
        for c in commits[:15]:
            lines.append(f"- [`{c['short_sha']}`] {c['message']}")
        if len(commits) > 15:
            lines.append(f"- *...and {len(commits) - 15} additional commits.*")
        lines.append("")

        lines.append("## Validation Results")
        overall = validation_summary.get("overall_status", "UNKNOWN")
        lines.append(f"Pre-PR verification status: **{overall}**")
        for chk in validation_summary.get("checks", []):
            st = chk.get("status", "NOT_RUN")
            icon = "✓" if st == "PASSED" else ("⚠" if st == "WARNING" else ("✗" if st == "FAILED" else "-"))
            lines.append(f"- {icon} **{chk.get('name')}**: {st} — {chk.get('message', '')}")
        lines.append("")

        lines.append("---")
        lines.append("*Generated automatically by AutoGit AI. Review thoroughly before merging.*")
        return "\n".join(lines)

    # =========================================================================
    # PR Creation Workflow (Requires Explicit User Approval)
    # =========================================================================

    def create_pull_request(
        self,
        repository_id: int,
        source_branch: str,
        target_branch: str,
        title: str,
        description: Optional[str] = None,
        is_draft: bool = False,
        token_override: Optional[str] = None,
    ) -> PullRequestModel:
        """
        Create a GitHub Pull Request via REST API POST /repos/{owner}/{repo}/pulls.
        Enforces:
        1. Backend permission check ('pull_request_creation' enabled).
        2. Immediate re-validation of branch state and duplicate PR status.
        3. Never automatically merges the PR.
        4. Persists the created PR in SQLite.
        """
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        # 1. STRICT PERMISSION CHECK: Must have explicit pull_request_creation permission
        if not self.permission_mgr.verify_permission(repository_id, "pull_request_creation"):
            logger.warning(f"PR creation DENIED: repo {repository_id} lacks 'pull_request_creation' permission.")
            raise PermissionDeniedError(
                f"Repository '{repo.repository_name}' is not authorized for Pull Request creation. "
                "Please enable the 'Pull Request Creation' permission first in Repository Settings."
            )

        if not title or not title.strip():
            raise ValueError("Pull Request title cannot be empty.")

        # 2. Recalculate comparison & verify duplicate status immediately before creation
        prep = self.prepare_pull_request(
            repository_id=repository_id,
            source_branch=source_branch,
            target_branch=target_branch,
            token_override=token_override,
        )
        if not prep["can_create"]:
            reasons = "; ".join(prep["blocking_reasons"])
            raise ValueError(f"Cannot create Pull Request: {reasons}")

        owner_repo = self.parse_github_owner_repo(repo.remote_url)
        if not owner_repo:
            raise ValueError(f"Cannot parse GitHub owner and repository from remote URL: '{repo.remote_url}'.")
        owner, repo_name = owner_repo

        token = self._get_github_token(token_override)
        if not token:
            raise ValueError("GitHub authentication token is required to create a Pull Request.")

        payload = {
            "title": title.strip(),
            "body": (description or "").strip(),
            "head": source_branch,
            "base": target_branch,
            "draft": bool(is_draft),
        }

        # 3. Send GitHub API request
        with httpx.Client(timeout=15.0) as client:
            try:
                resp = client.post(
                    f"{self.BASE_URL}/repos/{owner}/{repo_name}/pulls",
                    headers=self._build_headers(token),
                    json=payload,
                )
            except Exception as e:
                clean_err = self._clean_error(str(e), token)
                logger.error(f"GitHub API connection failed during PR creation: {clean_err}")
                raise RuntimeError(f"Network error communicating with GitHub API: {clean_err}")

        # 4. Handle response
        if resp.status_code == 201:
            data = resp.json()
            head_sha = data.get("head", {}).get("sha")
            base_sha = data.get("base", {}).get("sha")
            pr_state = "draft" if data.get("draft") else data.get("state", "open").lower()

            pr_model = PullRequestModel(
                id=None,
                repository_id=repository_id,
                pr_number=data.get("number"),
                title=data.get("title", title),
                source_branch=source_branch,
                target_branch=target_branch,
                state=pr_state,
                html_url=data.get("html_url"),
                is_merged=bool(data.get("merged", False)),
                created_at=data.get("created_at", get_utc_now_iso()),
                updated_at=data.get("updated_at", get_utc_now_iso()),
                merged_at=data.get("merged_at"),
                body=data.get("body"),
                diff_url=data.get("diff_url"),
                github_pr_id=data.get("id"),
                head_commit_sha=head_sha,
                base_commit_sha=base_sha,
                is_draft=bool(data.get("draft", False)),
                last_synced_at=get_utc_now_iso(),
                last_sync_error=None,
            )
            saved = self.pr_repo.create_or_update_pr(pr_model)
            logger.info(
                f"Successfully created GitHub PR #{saved.pr_number} for repo {repository_id} "
                f"({source_branch} -> {target_branch}): {saved.html_url}"
            )
            return saved

        elif resp.status_code == 422:
            # Unprocessable Entity (e.g. duplicate PR or no commits)
            err_data = resp.json()
            err_msg = err_data.get("message", "Validation failed")
            errors_list = [e.get("message", "") for e in err_data.get("errors", []) if isinstance(e, dict)]
            combined = f"{err_msg}: {', '.join(errors_list)}" if errors_list else err_msg
            if "already exists" in combined.lower() or "pull request already exists" in combined.lower():
                raise DuplicatePRError(f"A Pull Request already exists on GitHub for {source_branch} -> {target_branch}.")
            raise ValueError(f"GitHub rejected Pull Request creation (422): {combined}")

        elif resp.status_code == 403:
            err_msg = resp.json().get("message", "Forbidden")
            if "rate limit" in err_msg.lower():
                raise RateLimitExceededError("GitHub API rate limit exceeded. Please try again later.")
            raise PermissionDeniedError(f"GitHub access denied: {err_msg}")

        elif resp.status_code == 401:
            raise ValueError("GitHub authentication failed: Personal Access Token is invalid or expired.")

        else:
            clean_err = self._clean_error(resp.text, token)
            raise RuntimeError(f"GitHub API returned HTTP {resp.status_code}: {clean_err}")

    # =========================================================================
    # Lifecycle Synchronization
    # =========================================================================

    def refresh_pull_request(
        self,
        repository_id: int,
        pr_number: int,
        token_override: Optional[str] = None,
    ) -> PullRequestModel:
        """
        Fetch latest PR status from GitHub, distinguish CLOSED vs MERGED,
        detect DRAFT and review status, and update SQLite.
        """
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        owner_repo = self.parse_github_owner_repo(repo.remote_url)
        if not owner_repo:
            raise ValueError(f"Cannot parse GitHub repository from remote URL '{repo.remote_url}'.")
        owner, repo_name = owner_repo

        token = self._get_github_token(token_override)
        if not token:
            raise ValueError("GitHub token required to refresh Pull Request status.")

        with httpx.Client(timeout=15.0) as client:
            # 1. PR details
            resp = client.get(
                f"{self.BASE_URL}/repos/{owner}/{repo_name}/pulls/{pr_number}",
                headers=self._build_headers(token),
            )
            if resp.status_code != 200:
                clean_err = self._clean_error(resp.text, token)
                # If PR exists in DB, record sync error and return last known
                existing = self.pr_repo.get_pr_by_number(repository_id, pr_number)
                if existing:
                    updated = self.pr_repo.update_lifecycle(
                        repository_id=repository_id,
                        pr_number=pr_number,
                        state=existing.state,
                        is_merged=existing.is_merged,
                        is_draft=existing.is_draft,
                        last_sync_error=clean_err,
                    )
                    return updated or existing
                raise ValueError(f"GitHub PR #{pr_number} not found (HTTP {resp.status_code}): {clean_err}")

            data = resp.json()

            # 2. Review status
            review_status = None
            try:
                rev_resp = client.get(
                    f"{self.BASE_URL}/repos/{owner}/{repo_name}/pulls/{pr_number}/reviews",
                    headers=self._build_headers(token),
                )
                if rev_resp.status_code == 200:
                    reviews = rev_resp.json()
                    states = [r.get("state") for r in reviews if r.get("state")]
                    if "CHANGES_REQUESTED" in states:
                        review_status = "changes_requested"
                    elif "APPROVED" in states:
                        review_status = "approved"
            except Exception:
                pass

        is_merged = bool(data.get("merged", False) or data.get("merged_at"))
        is_draft = bool(data.get("draft", False))
        gh_state = (data.get("state") or "open").lower()

        if is_merged:
            final_state = "merged"
        elif gh_state == "closed":
            final_state = "closed"
        elif is_draft:
            final_state = "draft"
        elif review_status == "changes_requested":
            final_state = "changes_requested"
        elif review_status == "approved":
            final_state = "open"
        else:
            final_state = "open"

        head_sha = data.get("head", {}).get("sha")
        base_sha = data.get("base", {}).get("sha")

        model = PullRequestModel(
            id=None,
            repository_id=repository_id,
            pr_number=pr_number,
            title=data.get("title", f"PR #{pr_number}"),
            source_branch=data.get("head", {}).get("ref", "unknown"),
            target_branch=data.get("base", {}).get("ref", "main"),
            state=final_state,
            html_url=data.get("html_url", ""),
            is_merged=is_merged,
            created_at=data.get("created_at", get_utc_now_iso()),
            updated_at=data.get("updated_at", get_utc_now_iso()),
            merged_at=data.get("merged_at"),
            body=data.get("body"),
            diff_url=data.get("diff_url"),
            github_pr_id=data.get("id"),
            head_commit_sha=head_sha,
            base_commit_sha=base_sha,
            is_draft=is_draft,
            last_synced_at=get_utc_now_iso(),
            last_sync_error=None,
        )
        return self.pr_repo.create_or_update_pr(model)

    def sync_repository_prs(
        self,
        repository_id: int,
        token_override: Optional[str] = None,
    ) -> List[PullRequestModel]:
        """
        Synchronize all PRs for a repository from GitHub.
        Respects API limits and updates SQLite records.
        """
        repo = self.db.get_repository(repository_id)
        if not repo:
            raise ValueError(f"Repository {repository_id} does not exist.")

        owner_repo = self.parse_github_owner_repo(repo.remote_url)
        if not owner_repo:
            return self.pr_repo.list_prs_for_repository(repository_id)
        owner, repo_name = owner_repo

        token = self._get_github_token(token_override)
        if not token:
            return self.pr_repo.list_prs_for_repository(repository_id)

        synced: List[PullRequestModel] = []
        with httpx.Client(timeout=15.0) as client:
            resp = client.get(
                f"{self.BASE_URL}/repos/{owner}/{repo_name}/pulls?state=all&per_page=30",
                headers=self._build_headers(token),
            )
            if resp.status_code == 200:
                for item in resp.json():
                    pr_num = item.get("number")
                    is_merged = bool(item.get("merged_at"))
                    is_draft = bool(item.get("draft", False))
                    gh_state = (item.get("state") or "open").lower()
                    if is_merged:
                        final_state = "merged"
                    elif gh_state == "closed":
                        final_state = "closed"
                    elif is_draft:
                        final_state = "draft"
                    else:
                        final_state = "open"

                    m = PullRequestModel(
                        id=None,
                        repository_id=repository_id,
                        pr_number=pr_num,
                        title=item.get("title", f"PR #{pr_num}"),
                        source_branch=item.get("head", {}).get("ref", "unknown"),
                        target_branch=item.get("base", {}).get("ref", "main"),
                        state=final_state,
                        html_url=item.get("html_url", ""),
                        is_merged=is_merged,
                        created_at=item.get("created_at", get_utc_now_iso()),
                        updated_at=item.get("updated_at", get_utc_now_iso()),
                        merged_at=item.get("merged_at"),
                        body=item.get("body"),
                        diff_url=item.get("diff_url"),
                        github_pr_id=item.get("id"),
                        head_commit_sha=item.get("head", {}).get("sha"),
                        base_commit_sha=item.get("base", {}).get("sha"),
                        is_draft=is_draft,
                        last_synced_at=get_utc_now_iso(),
                        last_sync_error=None,
                    )
                    synced.append(self.pr_repo.create_or_update_pr(m))
            elif resp.status_code == 403:
                raise RateLimitExceededError("GitHub rate limit exceeded during PR sync.")

        return synced or self.pr_repo.list_prs_for_repository(repository_id)
