"""
AutoGit AI - Phase 4 Step 4: GitHub Pull Request Automation Test Suite.
Tests:
1. GitHub Authentication and Permission Enforcement (pull_request_creation).
2. Branch Discovery, Name Validation, and Comparison (ahead/behind, diff, secrets).
3. Pre-PR Autonomous Validation (ValidationAgent, tests, build, lint, secrets).
4. PR Preparation (comparison, validation, title/body generation, duplicate check, no mutation).
5. PR Creation with Explicit Approval (permission enforcement, re-validation, duplicate prevention, no auto-merge).
6. PR Lifecycle Tracking (OPEN, DRAFT, MERGED, CLOSED, CHANGES_REQUESTED, refresh).
7. SQLite Database Management & Idempotency (PullRequestRepository, migration).
8. FastAPI Endpoints Integration.
"""

from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from main import app
from core.permission_manager import PermissionDeniedError, PermissionManager
from database.db import DatabaseManager
from database.models import PullRequestModel, RepositoryModel
from database.pull_request_repository import PullRequestRepository
from integrations.github_pr_service import DuplicatePRError, GitHubPRService, RateLimitExceededError


# ─── Test Helpers ─────────────────────────────────────────────────────────────

def _create_test_repo_with_bare_remote(tmp_path: Path):
    """Create a local git repository paired with a bare remote repository."""
    bare_remote = tmp_path / "remote.git"
    bare_remote.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare"], cwd=bare_remote, check=True, capture_output=True)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=bare_remote, check=True, capture_output=True)

    local_repo = tmp_path / "local_repo"
    local_repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=local_repo, check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "AutoGit Tester"], cwd=local_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@autogit.ai"], cwd=local_repo, check=True)

    (local_repo / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=local_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=local_repo, check=True)

    subprocess.run(["git", "remote", "add", "origin", str(bare_remote)], cwd=local_repo, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=local_repo, check=True)

    return local_repo, bare_remote


def _mock_http_response(status_code: int, json_data: Any):
    """Create a mock httpx.Response object."""
    mock_resp = MagicMock()
    mock_resp.status_code = status_code
    mock_resp.json.return_value = json_data
    mock_resp.text = str(json_data)
    return mock_resp


# ─── Group 1: Authentication and Permission Enforcement ───────────────────────

class TestGitHubAuthenticationAndPermissions:
    """Verifies secure GitHub identity retrieval and repository-level PR permission enforcement."""

    def test_authenticated_user_retrieval(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_auth.db")
        service = GitHubPRService(database=db)

        mock_user = {"id": 12345, "login": "octocat", "name": "The Octocat", "html_url": "https://github.com/octocat"}
        with patch("httpx.Client.get", return_value=_mock_http_response(200, mock_user)):
            user = service.get_authenticated_user(token_override="valid_token_123")
            assert user["login"] == "octocat"
            assert user["id"] == 12345

    def test_invalid_token_rejected_with_clean_error(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_auth_inv.db")
        service = GitHubPRService(database=db)

        with patch("httpx.Client.get", return_value=_mock_http_response(401, {"message": "Bad credentials"})):
            with pytest.raises(ValueError, match="Token is invalid or expired"):
                service.get_authenticated_user(token_override="invalid_token_abc")

    def test_rate_limit_token_rejected(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_auth_rate.db")
        service = GitHubPRService(database=db)

        with patch("httpx.Client.get", return_value=_mock_http_response(403, {"message": "API rate limit exceeded"})):
            with pytest.raises(ValueError, match="rate limit exceeded"):
                service.get_authenticated_user(token_override="ratelimited_token")

    def test_pr_creation_permission_disabled_by_default(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_perm_def.db")
        repo = db.add_repository("PermTestRepo", str(tmp_path), remote_url="https://github.com/owner/repo.git")
        perm_mgr = PermissionManager(db)

        # Default policy: pull_request_creation must be False
        assert perm_mgr.verify_permission(repo.id, "pull_request_creation") is False

        # Attempting PR creation must raise PermissionDeniedError
        service = GitHubPRService(database=db, permission_mgr=perm_mgr)
        with pytest.raises(PermissionDeniedError, match="not authorized for Pull Request creation"):
            service.create_pull_request(
                repository_id=repo.id,
                source_branch="autogit/dev-1",
                target_branch="main",
                title="feat: test PR",
            )

    def test_pr_creation_permission_can_be_explicitly_enabled(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_perm_en.db")
        repo = db.add_repository("PermTestRepo2", str(tmp_path), remote_url="https://github.com/owner/repo.git")
        perm_mgr = PermissionManager(db)

        perm_mgr.update_permissions(repo.id, pull_request_creation_enabled=True)
        assert perm_mgr.verify_permission(repo.id, "pull_request_creation") is True

    def test_token_redaction_in_error_messages(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_redact.db")
        service = GitHubPRService(database=db)

        secret_token = "ghp_SecretTokenXYZ1234567890abcdef"
        raw_error = f"Failed to push with authorization token {secret_token} on remote."
        cleaned = service._clean_error(raw_error, secret_token)
        assert secret_token not in cleaned
        assert "***REDACTED_TOKEN***" in cleaned


# ─── Group 2: Branch Discovery and Comparison ─────────────────────────────────

class TestBranchDiscoveryAndComparison:
    """Verifies local and remote branch discovery, ref validation, and branch diffing."""

    def test_list_local_and_remote_branches(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_branches.db")
        repo = db.add_repository("BranchesRepo", str(local_repo), remote_url=str(bare_remote))
        service = GitHubPRService(database=db)

        # Create local dev branch
        subprocess.run(["git", "checkout", "-b", "autogit/dev-feat1"], cwd=local_repo, check=True)
        (local_repo / "f.txt").write_text("content", encoding="utf-8")
        subprocess.run(["git", "add", "f.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: branch commit"], cwd=local_repo, check=True)

        res = service.list_branches(repo.id)
        local_names = [b["name"] for b in res["local_branches"]]
        assert "main" in local_names
        assert "autogit/dev-feat1" in local_names
        assert res["default_branch"] == "main"

    def test_reject_same_source_and_target_branch(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_same_br.db")
        repo = db.add_repository("SameBrRepo", str(local_repo), remote_url=str(bare_remote))
        service = GitHubPRService(database=db)

        with pytest.raises(ValueError, match="Source branch and target branch cannot be the same"):
            service.compare_branches(repo.id, "main", "main")

    def test_reject_unsafe_branch_names(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_unsafe.db")
        repo = db.add_repository("UnsafeRepo", str(local_repo), remote_url=str(bare_remote))
        service = GitHubPRService(database=db)

        with pytest.raises(ValueError, match="Invalid or unsafe source branch name"):
            service.compare_branches(repo.id, "dev; rm -rf /", "main")

        with pytest.raises(ValueError, match="Invalid or unsafe source branch name"):
            service.compare_branches(repo.id, "autogit/dev-*", "main")

    def test_detect_unpushed_source_branch(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_unpushed.db")
        repo = db.add_repository("UnpushedRepo", str(local_repo), remote_url=str(bare_remote))
        service = GitHubPRService(database=db)

        # Create branch locally only (do not push)
        subprocess.run(["git", "checkout", "-b", "autogit/dev-unpushed"], cwd=local_repo, check=True)
        (local_repo / "new.txt").write_text("unpushed", encoding="utf-8")
        subprocess.run(["git", "add", "new.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "unpushed commit"], cwd=local_repo, check=True)

        comp = service.compare_branches(repo.id, "autogit/dev-unpushed", "main")
        assert comp["is_pushed"] is False
        assert comp["ahead_count"] == 1
        assert len(comp["changed_files"]) == 1
        assert comp["changed_files"][0]["filename"] == "new.txt"

    def test_compare_pushed_branch_with_commits_and_diff(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_pushed.db")
        repo = db.add_repository("PushedRepo", str(local_repo), remote_url=str(bare_remote))
        service = GitHubPRService(database=db)

        subprocess.run(["git", "checkout", "-b", "autogit/dev-pushed"], cwd=local_repo, check=True)
        (local_repo / "app.py").write_text("print('hello world')\n", encoding="utf-8")
        subprocess.run(["git", "add", "app.py"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: add app.py"], cwd=local_repo, check=True)
        subprocess.run(["git", "push", "-u", "origin", "autogit/dev-pushed"], cwd=local_repo, check=True)

        comp = service.compare_branches(repo.id, "autogit/dev-pushed", "main")
        assert comp["is_pushed"] is True
        assert comp["ahead_count"] == 1
        assert comp["behind_count"] == 0
        assert comp["commits"][0]["message"] == "feat: add app.py"
        assert comp["changed_files"][0]["filename"] == "app.py"


# ─── Group 3: Pre-PR Validation Safety ────────────────────────────────────────

class TestPrePRValidation:
    """Verifies that automated test failures or secret detections block PR creation."""

    def test_validation_passes_when_clean(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_val_clean.db")
        repo = db.add_repository("ValCleanRepo", str(local_repo), remote_url=str(bare_remote))
        service = GitHubPRService(database=db)

        val = service.run_validation(repo.id, "main", ["README.md"])
        assert val["can_create"] is True
        assert val["overall_status"] == "PASSED"
        assert len(val["blocking_reasons"]) == 0

    def test_validation_blocks_pr_when_secret_detected(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_val_sec.db")
        repo = db.add_repository("ValSecRepo", str(local_repo), remote_url=str(bare_remote))
        service = GitHubPRService(database=db)

        # Commit a file containing an API key pattern
        (local_repo / "secrets.env").write_text("GITHUB_TOKEN=ghp_123456789012345678901234567890123456\n", encoding="utf-8")
        subprocess.run(["git", "add", "secrets.env"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "add secrets"], cwd=local_repo, check=True)

        val = service.run_validation(repo.id, "main", ["secrets.env"])
        assert val["can_create"] is False
        assert val["overall_status"] == "FAILED"
        assert any("secret" in r.lower() for r in val["blocking_reasons"])

    def test_validation_blocks_pr_when_mandatory_tests_fail(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_val_fail.db")
        repo = db.add_repository("ValFailRepo", str(local_repo), remote_url=str(bare_remote))

        mock_validation_agent = MagicMock()
        mock_validation_agent.run_all_validations.return_value = {
            "overall_status": "FAILED",
            "all_passed": False,
            "secret_scan": {"has_secrets": False, "findings": []},
            "tests": {"status": "FAILED", "summary": "2 unit tests failed"},
            "lint": {"status": "PASSED"},
            "build": {"status": "PASSED"},
            "policy": {"is_valid": False},
        }

        service = GitHubPRService(database=db, validation_agent=mock_validation_agent)
        val = service.run_validation(repo.id, "main", ["README.md"])
        assert val["can_create"] is False
        assert val["overall_status"] == "FAILED"
        assert "Automated test suite failed." in val["blocking_reasons"]


# ─── Group 4: PR Preparation Workflow ─────────────────────────────────────────

class TestPRPreparation:
    """Verifies that PR preparation generates correct title, description, and eligibility without creating a PR."""

    def test_pr_preparation_generates_metadata_without_creating_pr(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_prep.db")
        repo = db.add_repository("PrepRepo", str(local_repo), remote_url=str(bare_remote))
        pr_repo = PullRequestRepository(db)
        service = GitHubPRService(database=db, pr_repo=pr_repo)

        # Create and push branch
        subprocess.run(["git", "checkout", "-b", "autogit/dev-login-flow"], cwd=local_repo, check=True)
        (local_repo / "auth.py").write_text("def login(): pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "auth.py"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: implement login authentication flow"], cwd=local_repo, check=True)
        subprocess.run(["git", "push", "-u", "origin", "autogit/dev-login-flow"], cwd=local_repo, check=True)

        prep = service.prepare_pull_request(repo.id, "autogit/dev-login-flow", "main")
        assert prep["can_create"] is True
        assert prep["is_pushed"] is True
        assert prep["ahead_count"] == 1
        assert "feat: implement login authentication flow" in prep["suggested_title"]
        assert "## Summary" in prep["suggested_body"]
        assert "## Changes" in prep["suggested_body"]
        assert "## Validation Results" in prep["suggested_body"]

        # CRITICAL: Verify NO PR record was created in the database during preparation
        assert len(pr_repo.list_prs_for_repository(repo.id)) == 0

    def test_pr_preparation_detects_existing_open_pr(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_prep_dup.db")
        repo = db.add_repository("PrepDupRepo", str(local_repo), remote_url=str(bare_remote))
        pr_repo = PullRequestRepository(db)
        service = GitHubPRService(database=db, pr_repo=pr_repo)

        # Push branch
        subprocess.run(["git", "checkout", "-b", "autogit/dev-existing"], cwd=local_repo, check=True)
        (local_repo / "f.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "f.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: existing test"], cwd=local_repo, check=True)
        subprocess.run(["git", "push", "-u", "origin", "autogit/dev-existing"], cwd=local_repo, check=True)

        # Pre-seed an open PR record
        pr_repo.create_or_update_pr(
            PullRequestModel(
                id=None,
                repository_id=repo.id,
                pr_number=42,
                title="Existing PR",
                source_branch="autogit/dev-existing",
                target_branch="main",
                state="open",
                html_url="https://github.com/owner/repo/pull/42",
            )
        )

        prep = service.prepare_pull_request(repo.id, "autogit/dev-existing", "main")
        assert prep["can_create"] is False
        assert prep["existing_pr_number"] == 42
        assert any("already exists" in r for r in prep["blocking_reasons"])


# ─── Group 5: PR Creation and Safeguards ───────────────────────────────────────

class TestPRCreationAndSafeguards:
    """Verifies PR creation through GitHub REST API, duplicate prevention, and permission checks."""

    def test_successful_pr_creation_with_permission(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_create_ok.db")
        repo = db.add_repository("CreateOkRepo", str(local_repo), remote_url="https://github.com/testowner/testrepo.git")
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo.id, pull_request_creation_enabled=True)

        pr_repo = PullRequestRepository(db)
        service = GitHubPRService(database=db, permission_mgr=perm_mgr, pr_repo=pr_repo)

        # Create & push branch locally
        subprocess.run(["git", "checkout", "-b", "autogit/dev-safe"], cwd=local_repo, check=True)
        (local_repo / "feat.py").write_text("code", encoding="utf-8")
        subprocess.run(["git", "add", "feat.py"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: safe feature"], cwd=local_repo, check=True)
        subprocess.run(["git", "push", "-u", "origin", "autogit/dev-safe"], cwd=local_repo, check=True)

        mock_pr_response = {
            "id": 987654,
            "number": 101,
            "title": "feat: safe feature",
            "body": "Detailed description",
            "state": "open",
            "draft": False,
            "merged": False,
            "html_url": "https://github.com/testowner/testrepo/pull/101",
            "created_at": "2026-11-16T12:00:00Z",
            "updated_at": "2026-11-16T12:00:00Z",
            "head": {"sha": "abc1234", "ref": "autogit/dev-safe"},
            "base": {"sha": "base1234", "ref": "main"},
        }

        # Mock compare and branch endpoints for preparation step, and POST /pulls for creation
        def mock_client_route(url, *args, **kwargs):
            if "/branches/autogit/dev-safe" in url:
                return _mock_http_response(200, {"commit": {"sha": subprocess.run(["git", "rev-parse", "HEAD"], cwd=local_repo, capture_output=True, text=True).stdout.strip()}})
            if "/compare/" in url:
                return _mock_http_response(200, {"ahead_by": 1, "behind_by": 0, "commits": [{"sha": "abc1234", "commit": {"message": "feat: safe feature"}}], "files": [{"filename": "feat.py", "status": "added", "additions": 1, "deletions": 0}]})
            if "/pulls" in url and "state=open" in url:
                return _mock_http_response(200, [])
            return _mock_http_response(404, {})

        with patch("httpx.Client.get", side_effect=mock_client_route), \
             patch("httpx.Client.post", return_value=_mock_http_response(201, mock_pr_response)):

            pr = service.create_pull_request(
                repository_id=repo.id,
                source_branch="autogit/dev-safe",
                target_branch="main",
                title="feat: safe feature",
                description="Detailed description",
                is_draft=False,
                token_override="valid_token_123",
            )

            assert pr.pr_number == 101
            assert pr.state == "open"
            assert pr.is_merged is False
            assert pr.html_url == "https://github.com/testowner/testrepo/pull/101"

            # Verify persisted in SQLite
            persisted = pr_repo.get_pr_by_number(repo.id, 101)
            assert persisted is not None
            assert persisted.title == "feat: safe feature"
            assert persisted.github_pr_id == 987654

    def test_duplicate_pr_rejected_with_conflict(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_dup_err.db")
        repo = db.add_repository("DupRepo", str(local_repo), remote_url="https://github.com/owner/repo.git")
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo.id, pull_request_creation_enabled=True)

        service = GitHubPRService(database=db, permission_mgr=perm_mgr)

        subprocess.run(["git", "checkout", "-b", "autogit/dev-dup"], cwd=local_repo, check=True)
        (local_repo / "f.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "f.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "c1"], cwd=local_repo, check=True)
        subprocess.run(["git", "push", "-u", "origin", "autogit/dev-dup"], cwd=local_repo, check=True)

        # Pre-seed open PR locally
        service.pr_repo.create_or_update_pr(
            PullRequestModel(
                id=None,
                repository_id=repo.id,
                pr_number=55,
                title="Already Open",
                source_branch="autogit/dev-dup",
                target_branch="main",
                state="open",
                html_url="https://github.com/owner/repo/pull/55",
            )
        )

        with pytest.raises(ValueError, match="already exists"):
            service.create_pull_request(
                repository_id=repo.id,
                source_branch="autogit/dev-dup",
                target_branch="main",
                title="duplicate PR attempt",
                token_override="tok",
            )


# ─── Group 6: PR Lifecycle and Synchronization ────────────────────────────────

class TestPRLifecycleAndSync:
    """Verifies lifecycle tracking: OPEN, DRAFT, MERGED, CLOSED, CHANGES_REQUESTED."""

    def test_distinguish_closed_vs_merged_pr(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_lifecycle.db")
        repo = db.add_repository("LifecycleRepo", str(tmp_path), remote_url="https://github.com/owner/repo.git")
        pr_repo = PullRequestRepository(db)
        service = GitHubPRService(database=db, pr_repo=pr_repo)

        # 1. Closed without merge
        closed_gh_response = {
            "id": 11,
            "number": 11,
            "title": "Closed PR",
            "state": "closed",
            "merged": False,
            "merged_at": None,
            "draft": False,
            "html_url": "https://github.com/owner/repo/pull/11",
            "head": {"ref": "dev-11", "sha": "sha11"},
            "base": {"ref": "main", "sha": "shabase"},
        }
        with patch("httpx.Client.get", return_value=_mock_http_response(200, closed_gh_response)):
            pr11 = service.refresh_pull_request(repo.id, 11, token_override="tok")
            assert pr11.state == "closed"
            assert pr11.is_merged is False

        # 2. Actually merged
        merged_gh_response = {
            "id": 12,
            "number": 12,
            "title": "Merged PR",
            "state": "closed",
            "merged": True,
            "merged_at": "2026-11-16T13:00:00Z",
            "draft": False,
            "html_url": "https://github.com/owner/repo/pull/12",
            "head": {"ref": "dev-12", "sha": "sha12"},
            "base": {"ref": "main", "sha": "shabase"},
        }
        with patch("httpx.Client.get", return_value=_mock_http_response(200, merged_gh_response)):
            pr12 = service.refresh_pull_request(repo.id, 12, token_override="tok")
            assert pr12.state == "merged"
            assert pr12.is_merged is True
            assert pr12.merged_at == "2026-11-16T13:00:00Z"

    def test_detect_changes_requested_status(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_rev.db")
        repo = db.add_repository("RevRepo", str(tmp_path), remote_url="https://github.com/owner/repo.git")
        pr_repo = PullRequestRepository(db)
        service = GitHubPRService(database=db, pr_repo=pr_repo)

        pr_data = {
            "id": 15,
            "number": 15,
            "title": "PR with review",
            "state": "open",
            "merged": False,
            "draft": False,
            "html_url": "https://github.com/owner/repo/pull/15",
            "head": {"ref": "dev-15"},
            "base": {"ref": "main"},
        }

        def mock_get(url, *args, **kwargs):
            if "/reviews" in url:
                return _mock_http_response(200, [{"state": "CHANGES_REQUESTED"}])
            return _mock_http_response(200, pr_data)

        with patch("httpx.Client.get", side_effect=mock_get):
            pr15 = service.refresh_pull_request(repo.id, 15, token_override="tok")
            assert pr15.state == "changes_requested"

    def test_failed_refresh_preserves_last_known_valid_data(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_preserve.db")
        repo = db.add_repository("PreserveRepo", str(tmp_path), remote_url="https://github.com/owner/repo.git")
        pr_repo = PullRequestRepository(db)
        service = GitHubPRService(database=db, pr_repo=pr_repo)

        # Seed initial known valid state
        pr_repo.create_or_update_pr(
            PullRequestModel(
                id=None,
                repository_id=repo.id,
                pr_number=20,
                title="Known Valid PR",
                source_branch="dev-20",
                target_branch="main",
                state="open",
                html_url="https://github.com/owner/repo/pull/20",
            )
        )

        # GitHub returns 500 server error
        with patch("httpx.Client.get", return_value=_mock_http_response(500, {"message": "Internal error"})):
            res = service.refresh_pull_request(repo.id, 20, token_override="tok")
            # State preserved as open, error recorded
            assert res.state == "open"
            assert res.pr_number == 20
            assert res.last_sync_error is not None


# ─── Group 7: Database Management & Idempotency ────────────────────────────────

class TestPRDatabaseManagement:
    """Verifies SQLite persistence, idempotency, unique constraints, and schema migration."""

    def test_idempotent_upsert(self, tmp_path):
        db = DatabaseManager(tmp_path / "test_db_idem.db")
        repo = db.add_repository("DBRepo", str(tmp_path))
        pr_repo = PullRequestRepository(db)

        model1 = PullRequestModel(
            id=None,
            repository_id=repo.id,
            pr_number=1,
            title="Initial Title",
            source_branch="dev",
            target_branch="main",
            state="open",
            html_url="https://github.com/repo/pull/1",
        )
        saved1 = pr_repo.create_or_update_pr(model1)
        assert saved1.id is not None

        # Update same (repository_id, pr_number)
        model2 = PullRequestModel(
            id=None,
            repository_id=repo.id,
            pr_number=1,
            title="Updated Title",
            source_branch="dev",
            target_branch="main",
            state="merged",
            html_url="https://github.com/repo/pull/1",
            is_merged=True,
        )
        saved2 = pr_repo.create_or_update_pr(model2)

        # Count must remain 1
        all_prs = pr_repo.list_prs_for_repository(repo.id)
        assert len(all_prs) == 1
        assert all_prs[0].title == "Updated Title"
        assert all_prs[0].state == "merged"
        assert all_prs[0].is_merged is True


# ─── Group 8: FastAPI Endpoint Integration ────────────────────────────────────

class TestPRAPIEndpoints:
    """Verifies FastAPI REST endpoints integration."""

    def test_branches_endpoint(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_api_br.db")
        repo = db.add_repository("ApiBrRepo", str(local_repo), remote_url=str(bare_remote))

        from api.routes import get_db
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)

        try:
            resp = client.get(f"/api/v1/github/repositories/{repo.id}/branches")
            assert resp.status_code == 200
            data = resp.json()
            assert data["repository_id"] == repo.id
            assert "main" in [b["name"] for b in data["local_branches"]]
        finally:
            app.dependency_overrides.clear()

    def test_prepare_endpoint_does_not_create_pr(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_api_prep.db")
        repo = db.add_repository("ApiPrepRepo", str(local_repo), remote_url=str(bare_remote))

        subprocess.run(["git", "checkout", "-b", "autogit/dev-api-prep"], cwd=local_repo, check=True)
        (local_repo / "api.py").write_text("API test", encoding="utf-8")
        subprocess.run(["git", "add", "api.py"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: api test"], cwd=local_repo, check=True)
        subprocess.run(["git", "push", "-u", "origin", "autogit/dev-api-prep"], cwd=local_repo, check=True)

        from api.routes import get_db
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)

        try:
            resp = client.post(
                f"/api/v1/github/pull-requests/{repo.id}/prepare",
                json={"source_branch": "autogit/dev-api-prep", "target_branch": "main"},
            )
            assert resp.status_code == 200
            data = resp.json()
            assert data["can_create"] is True
            assert data["ahead_count"] == 1
            assert "feat: api test" in data["suggested_title"]

            # Verify no PR in list
            list_resp = client.get(f"/api/v1/github/pull-requests/{repo.id}")
            assert list_resp.status_code == 200
            assert len(list_resp.json()) == 0
        finally:
            app.dependency_overrides.clear()

    def test_create_endpoint_enforces_backend_permission(self, tmp_path):
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db = DatabaseManager(tmp_path / "test_api_perm.db")
        repo = db.add_repository("ApiPermRepo", str(local_repo), remote_url=str(bare_remote))

        from api.routes import get_db
        app.dependency_overrides[get_db] = lambda: db
        client = TestClient(app)

        try:
            # PR creation permission is DISABLED by default -> 403 Forbidden
            resp = client.post(
                f"/api/v1/github/pull-requests/{repo.id}",
                json={
                    "source_branch": "main",
                    "target_branch": "main",
                    "title": "Forbidden PR",
                },
            )
            assert resp.status_code == 403
            assert "not authorized for Pull Request creation" in resp.json()["detail"]
        finally:
            app.dependency_overrides.clear()
