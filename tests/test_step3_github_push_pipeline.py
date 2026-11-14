"""
Comprehensive Test Suite for AutoGit AI Step 3:
Secure GitHub Push Pipeline Integration, Remote Commit Verification, and Sync Status Management.

Test Groups:
- Group A: Credential Integration & Token Masking
- Group B: Accurate Branch Selection (autogit/dev-* isolation vs main)
- Group C: Remote Commit Verification (Exact match, Remote advanced, Unreachable, Non-fast-forward)
- Group D: Permission Enforcement (remote_push permission required, independent of other permissions)
- Group E: Database Persistence & State Transitions
- Group F: API Endpoints (/github/push, /github/sync-status, /github/pending, /github/push-history, /github/retry)
"""

import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from typing import Tuple
import pytest
from fastapi.testclient import TestClient

from config.settings import settings
from core.git_manager import GitManager
from core.permission_manager import PermissionDeniedError, PermissionManager
from database.db import DatabaseManager
from database.execution_repository import ExecutionRepository
from database.models import ExecutionHistoryModel
from database.sync_repository import SyncRepository
from integrations.github_sync import GitHubSyncEngine
from main import app


def _create_test_repo_with_bare_remote(tmp_path: Path) -> Tuple[Path, Path]:
    """
    Create a local git repository and a bare upstream remote.
    Returns (local_repo_path, bare_remote_path).
    """
    bare_remote = tmp_path / "remote.git"
    bare_remote.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "--bare", str(bare_remote)], check=True, capture_output=True)
    # Ensure bare remote HEAD points to main (Git may default to master)
    subprocess.run(["git", "symbolic-ref", "HEAD", "refs/heads/main"], cwd=bare_remote, check=True)

    local_repo = tmp_path / "local_repo"
    local_repo.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-b", "main", str(local_repo)], check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "TestUser"], cwd=local_repo, check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=local_repo, check=True)

    # Initial commit on main
    init_file = local_repo / "README.md"
    init_file.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=local_repo, check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=local_repo, check=True)

    # Add remote
    subprocess.run(["git", "remote", "add", "origin", str(bare_remote)], cwd=local_repo, check=True)
    subprocess.run(["git", "push", "-u", "origin", "main"], cwd=local_repo, check=True, capture_output=True)

    return local_repo, bare_remote


# ============================================================================
# Group A: Credential Integration & Token Masking
# ============================================================================

class TestCredentialIntegrationAndSafety:
    """Verifies that credentials are never leaked into arguments, URLs, config, or logs."""

    def test_token_absent_from_git_config_and_urls(self, tmp_path):
        """Pushing to remote must not alter .git/config to store tokens or credentials."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_a.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoA", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr)

        # Create a new commit to push
        (local_repo / "file1.txt").write_text("content1", encoding="utf-8")
        subprocess.run(["git", "add", "file1.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: file1"], cwd=local_repo, check=True)

        dummy_token = "ghp_SECRET_TOKEN_DO_NOT_LEAK_12345"
        res = engine.push_repository(repo_model.id, branch="main", token_override=dummy_token)
        assert res["success"] is True

        # Check .git/config
        config_content = (local_repo / ".git" / "config").read_text(encoding="utf-8", errors="ignore")
        assert dummy_token not in config_content
        assert "ghp_" not in config_content

    def test_authentication_failure_reported_cleanly(self, tmp_path):
        """When an invalid HTTPS credential fails against GitHub, error is safe and classified."""
        db_file = tmp_path / "test_auth_fail.db"
        db = DatabaseManager(db_file)
        local_repo = tmp_path / "dummy_repo"
        local_repo.mkdir()
        subprocess.run(["git", "init", "-b", "main", str(local_repo)], check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "TestUser"], cwd=local_repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=local_repo, check=True)
        (local_repo / "README.md").write_text("content", encoding="utf-8")
        subprocess.run(["git", "add", "."], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "initial"], cwd=local_repo, check=True)

        # Set remote to non-existent GitHub repo to trigger 401/auth failure
        subprocess.run(
            ["git", "remote", "add", "origin", "https://github.com/autogit-nonexistent-disposable/repo.git"],
            cwd=local_repo, check=True
        )

        repo_model = db.add_repository("DummyRepo", str(local_repo))
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr)
        bad_token = "ghp_INVALID_EXPIRED_TOKEN_99999"

        res = engine.push_repository(repo_model.id, branch="main", token_override=bad_token)
        assert res["success"] is False
        assert res["push_sync_status"] == "PUSH_FAILED"
        # Dummy token must NOT be leaked in error message
        assert bad_token not in str(res.get("error"))


# ============================================================================
# Group B: Accurate Branch Selection (autogit/dev-* isolation vs main)
# ============================================================================

class TestBranchSelectionAndIsolation:
    """Verifies that autonomous commits on autogit/dev-* branches are never pushed to main."""

    def test_push_autonomous_branch_targets_dev_branch_not_main(self, tmp_path):
        """Pushing an autonomous commit must push its autogit/dev-* branch, not main."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_b.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoB", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        exec_repo = ExecutionRepository(db)
        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr, exec_repo=exec_repo)

        # Create an autonomous development branch
        dev_branch = "autogit/dev-20261113-143000"
        subprocess.run(["git", "checkout", "-b", dev_branch], cwd=local_repo, check=True)
        (local_repo / "auto_feature.py").write_text("def auto(): pass\n", encoding="utf-8")
        subprocess.run(["git", "add", "auto_feature.py"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: autonomous feature"], cwd=local_repo, check=True)

        # Get commit hash
        commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        # Switch local HEAD back to main (simulating session completion)
        subprocess.run(["git", "checkout", "main"], cwd=local_repo, check=True)
        main_tip = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()
        assert main_tip != commit_hash

        # Create execution record pointing to the dev branch
        exec_model = exec_repo.create_execution(
            repository_id=repo_model.id,
            execution_mode="auto",
            status="committed",
            commit_hash=commit_hash,
            commit_message="feat: autonomous feature",
        )
        exec_repo.update_sync_status(
            execution_id=exec_model.id,
            push_sync_status="READY_TO_PUSH",
            branch_name=dev_branch,
            source_branch=dev_branch,
            local_commit_hash=commit_hash,
        )

        # Push through execution_id
        res = engine.push_repository(
            repository_id=repo_model.id,
            execution_id=exec_model.id,
        )

        assert res["success"] is True
        assert res["branch"] == dev_branch
        assert res["target_branch"] == dev_branch
        assert res["push_sync_status"] == "PUSHED"
        assert res["verification_status"] == "EXACT_MATCH"

        # Verify on bare remote: dev_branch must exist and have the commit
        remote_dev_tip = subprocess.run(
            ["git", "rev-parse", f"refs/heads/{dev_branch}"],
            cwd=bare_remote, check=True, capture_output=True, text=True
        ).stdout.strip()
        assert remote_dev_tip == commit_hash

        # Verify on bare remote: main must NOT contain the commit!
        remote_main_tip = subprocess.run(
            ["git", "rev-parse", "refs/heads/main"],
            cwd=bare_remote, check=True, capture_output=True, text=True
        ).stdout.strip()
        assert remote_main_tip == main_tip
        assert remote_main_tip != commit_hash

    def test_push_rejects_unrelated_commit_not_on_branch(self, tmp_path):
        """If user specifies a branch that does not contain the commit, reject."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_b2.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoB2", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr)

        # Create commit on a feature branch
        subprocess.run(["git", "checkout", "-b", "feature-x"], cwd=local_repo, check=True)
        (local_repo / "x.txt").write_text("x", encoding="utf-8")
        subprocess.run(["git", "add", "x.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: x"], cwd=local_repo, check=True)
        x_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        # Switch back to main
        subprocess.run(["git", "checkout", "main"], cwd=local_repo, check=True)

        # Attempt to push commit x specifying branch="main" (where it does not exist)
        with pytest.raises(ValueError, match="not reachable from source branch"):
            engine.push_repository(
                repository_id=repo_model.id,
                branch="main",
                commit_hash=x_commit,
            )


# ============================================================================
# Group C: Remote Commit Verification (Ancestry & Advanced Checks)
# ============================================================================

class TestRemoteCommitVerification:
    """Verifies that remote verification correctly identifies exact matches, advanced remotes, and failures."""

    def test_verification_exact_match(self, tmp_path):
        """When local commit matches the remote branch tip exactly -> EXACT_MATCH."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_c1.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoC1", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        exec_repo = ExecutionRepository(db)
        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr, exec_repo=exec_repo)

        (local_repo / "doc.md").write_text("Documentation\n", encoding="utf-8")
        subprocess.run(["git", "add", "doc.md"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "docs: update"], cwd=local_repo, check=True)
        commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        exec_model = exec_repo.create_execution(
            repository_id=repo_model.id,
            execution_mode="smart",
            status="committed",
            commit_hash=commit_hash,
            commit_message="docs: update",
        )

        res = engine.push_repository(repo_model.id, execution_id=exec_model.id, branch="main")
        assert res["success"] is True
        assert res["push_sync_status"] == "PUSHED"
        assert res["verification_status"] == "EXACT_MATCH"
        assert res["remote_advanced"] is False
        assert res["remote_commit_hash"] == commit_hash

    def test_verification_remote_advanced_ancestor_reachable(self, tmp_path):
        """When remote branch advanced after our commit, but our commit is reachable -> COMMIT_REACHABLE_REMOTE_ADVANCED."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_c2.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoC2", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        exec_repo = ExecutionRepository(db)
        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr, exec_repo=exec_repo)

        # Commit 1 (the one we track in execution_history)
        (local_repo / "f1.txt").write_text("1", encoding="utf-8")
        subprocess.run(["git", "add", "f1.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "commit 1"], cwd=local_repo, check=True)
        commit_1 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        exec_model = exec_repo.create_execution(
            repository_id=repo_model.id,
            execution_mode="smart",
            status="committed",
            commit_hash=commit_1,
            commit_message="commit 1",
        )

        # Commit 2 (remote will advance with this commit on top of commit 1)
        (local_repo / "f2.txt").write_text("2", encoding="utf-8")
        subprocess.run(["git", "add", "f2.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "commit 2"], cwd=local_repo, check=True)
        commit_2 = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        # Push with execution_id pointing to commit_1
        # The branch push will push the whole branch (including commit 2)
        res = engine.push_repository(repo_model.id, execution_id=exec_model.id, branch="main")

        assert res["success"] is True
        assert res["push_sync_status"] == "PUSHED"
        assert res["verification_status"] == "COMMIT_REACHABLE_REMOTE_ADVANCED"
        assert res["remote_advanced"] is True
        assert res["remote_commit_hash"] == commit_2
        assert res["local_commit_hash"] == commit_1

    def test_non_fast_forward_conflict_rejected_without_force(self, tmp_path):
        """When remote branch has diverged, push is rejected with REMOTE_CONFLICT without force push."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_c3.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoC3", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        exec_repo = ExecutionRepository(db)
        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr, exec_repo=exec_repo)

        # Advance remote directly via a clone
        other_clone = tmp_path / "other_clone"
        subprocess.run(
            ["git", "clone", "-b", "main", str(bare_remote), str(other_clone)],
            check=True, capture_output=True
        )
        subprocess.run(["git", "config", "user.name", "OtherUser"], cwd=other_clone, check=True)
        subprocess.run(["git", "config", "user.email", "other@example.com"], cwd=other_clone, check=True)
        # Ensure we are on main (bare repo HEAD may default to master on some systems)
        subprocess.run(["git", "checkout", "-B", "main"], cwd=other_clone, check=True, capture_output=True)
        (other_clone / "other.txt").write_text("remote change", encoding="utf-8")
        subprocess.run(["git", "add", "other.txt"], cwd=other_clone, check=True)
        subprocess.run(["git", "commit", "-m", "remote commit"], cwd=other_clone, check=True)
        subprocess.run(["git", "push", "origin", "HEAD:main"], cwd=other_clone, check=True, capture_output=True)

        # Make divergent commit on local_repo
        (local_repo / "local.txt").write_text("local change", encoding="utf-8")
        subprocess.run(["git", "add", "local.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "local commit"], cwd=local_repo, check=True)
        local_commit = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        exec_model = exec_repo.create_execution(
            repository_id=repo_model.id,
            execution_mode="smart",
            status="committed",
            commit_hash=local_commit,
            commit_message="local commit",
        )

        res = engine.push_repository(repo_model.id, execution_id=exec_model.id, branch="main")
        assert res["success"] is False
        assert res["push_sync_status"] == "REMOTE_CONFLICT"

        # Check execution record in DB
        updated_exec = exec_repo.get_execution(exec_model.id)
        assert updated_exec.push_sync_status == "REMOTE_CONFLICT"


# ============================================================================
# Group D: Permission Enforcement
# ============================================================================

class TestPermissionEnforcement:
    """Verifies that remote_push permission is strictly required and independent of other permissions."""

    def test_push_fails_when_remote_push_disabled(self, tmp_path):
        """When remote_push is not enabled, push raises PermissionDeniedError."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_perm.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoPerm", str(local_repo), remote_url=str(bare_remote))

        perm_mgr = PermissionManager(db)
        # Enable all permissions EXCEPT remote_push
        perm_mgr.update_permissions(
            repo_model.id,
            monitoring_enabled=True,
            ai_analysis_enabled=True,
            autonomous_development_enabled=True,
            smart_commit_enabled=True,
            auto_commit_enabled=True,
            remote_push_enabled=False,
        )

        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr)

        with pytest.raises(PermissionDeniedError, match="not authorized for remote push"):
            engine.push_repository(repo_model.id, branch="main")

    def test_permission_revocation_blocks_subsequent_push(self, tmp_path):
        """Revoking permission immediately blocks push."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_revoke.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoRevoke", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr)

        # Revoke permission
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=False)

        with pytest.raises(PermissionDeniedError):
            engine.push_repository(repo_model.id, branch="main")


# ============================================================================
# Group E: Database Persistence & State Transitions
# ============================================================================

class TestDatabasePersistenceAndStateTransitions:
    """Verifies SQLite updates, sync status tracking, and audit log entries."""

    def test_sync_status_persisted_to_execution_history(self, tmp_path):
        """Successful push records all Step 2 columns in execution_history."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_db.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoDB", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        exec_repo = ExecutionRepository(db)
        engine = GitHubSyncEngine(database=db, permission_mgr=perm_mgr, exec_repo=exec_repo)

        (local_repo / "db_test.txt").write_text("db", encoding="utf-8")
        subprocess.run(["git", "add", "db_test.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: db test"], cwd=local_repo, check=True)
        commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        exec_model = exec_repo.create_execution(
            repo_model.id, execution_mode="smart", status="committed", commit_hash=commit_hash
        )

        res = engine.push_repository(repo_model.id, execution_id=exec_model.id, branch="main")
        assert res["success"] is True

        # Check DB row directly
        updated = exec_repo.get_execution(exec_model.id)
        assert updated.push_sync_status == "PUSHED"
        assert updated.verification_status == "EXACT_MATCH"
        assert updated.local_commit_hash == commit_hash
        assert updated.remote_commit_hash == commit_hash
        assert updated.source_branch == "main"
        assert updated.target_branch == "main"
        assert updated.remote_name == "origin"
        assert updated.push_timestamp is not None
        assert updated.push_error is None

    def test_pending_commits_listing(self, tmp_path):
        """get_pending_commits returns unpushed and unverified commits."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_pending.db"
        db = DatabaseManager(db_file)
        repo_model = db.add_repository("TestRepoPending", str(local_repo), remote_url=str(bare_remote))
        exec_repo = ExecutionRepository(db)
        engine = GitHubSyncEngine(database=db, exec_repo=exec_repo)

        # Insert 2 committed executions
        e1 = exec_repo.create_execution(repo_model.id, "smart", "committed", "hash1", "commit 1")
        exec_repo.update_sync_status(e1.id, "LOCAL_ONLY")

        e2 = exec_repo.create_execution(repo_model.id, "smart", "committed", "hash2", "commit 2")
        exec_repo.update_sync_status(e2.id, "PUSHED")  # Already pushed

        pending = engine.get_pending_commits(repo_model.id)
        pending_ids = [p["execution_id"] for p in pending]
        assert e1.id in pending_ids
        assert e2.id not in pending_ids


# ============================================================================
# Group F: API Endpoints Integration
# ============================================================================

class TestApiEndpointsIntegration:
    """Verifies that FastAPI endpoints correctly enforce permissions, execute push, and return data."""

    def test_api_push_endpoint_success(self, tmp_path, monkeypatch):
        """POST /api/v1/github/push successfully pushes commit and returns verification details."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_api.db"
        test_db = DatabaseManager(db_file)
        repo_model = test_db.add_repository("TestRepoApi", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(test_db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        exec_repo = ExecutionRepository(test_db)
        (local_repo / "api_test.txt").write_text("api", encoding="utf-8")
        subprocess.run(["git", "add", "api_test.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: api test"], cwd=local_repo, check=True)
        commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        exec_model = exec_repo.create_execution(
            repo_model.id, "smart", "committed", commit_hash, "feat: api test"
        )

        from api.routes import get_db
        app.dependency_overrides[get_db] = lambda: test_db
        client = TestClient(app)

        try:
            payload = {
                "repository_id": repo_model.id,
                "execution_id": exec_model.id,
                "remote_name": "origin",
            }
            resp = client.post("/api/v1/github/push", json=payload)
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["push_sync_status"] == "PUSHED"
            assert data["verification_status"] == "EXACT_MATCH"
            assert data["remote_verified"] is True
        finally:
            app.dependency_overrides.clear()

    def test_api_push_endpoint_permission_denied_403(self, tmp_path):
        """POST /api/v1/github/push returns 403 when remote_push permission is disabled."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_api_403.db"
        test_db = DatabaseManager(db_file)
        repo_model = test_db.add_repository("TestRepo403", str(local_repo), remote_url=str(bare_remote))

        from api.routes import get_db
        app.dependency_overrides[get_db] = lambda: test_db
        client = TestClient(app)

        try:
            payload = {
                "repository_id": repo_model.id,
                "remote_name": "origin",
            }
            resp = client.post("/api/v1/github/push", json=payload)
            assert resp.status_code == 403
            assert "not authorized for remote push" in resp.json()["detail"].lower()
        finally:
            app.dependency_overrides.clear()

    def test_api_sync_status_endpoint(self, tmp_path):
        """GET /api/v1/github/sync-status/{repo_id} returns accurate sync status."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_api_status.db"
        test_db = DatabaseManager(db_file)
        repo_model = test_db.add_repository("TestRepoStatus", str(local_repo), remote_url=str(bare_remote))

        from api.routes import get_db
        app.dependency_overrides[get_db] = lambda: test_db
        client = TestClient(app)

        try:
            resp = client.get(f"/api/v1/github/sync-status/{repo_model.id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["repository_id"] == repo_model.id
            assert data["repository_name"] == "TestRepoStatus"
            assert "push_sync_status" in data
        finally:
            app.dependency_overrides.clear()

    def test_api_retry_endpoint(self, tmp_path):
        """POST /api/v1/github/retry/{execution_id} retries a push."""
        local_repo, bare_remote = _create_test_repo_with_bare_remote(tmp_path)
        db_file = tmp_path / "test_api_retry.db"
        test_db = DatabaseManager(db_file)
        repo_model = test_db.add_repository("TestRepoRetry", str(local_repo), remote_url=str(bare_remote))
        perm_mgr = PermissionManager(test_db)
        perm_mgr.update_permissions(repo_model.id, remote_push_enabled=True)

        exec_repo = ExecutionRepository(test_db)
        (local_repo / "retry_test.txt").write_text("retry", encoding="utf-8")
        subprocess.run(["git", "add", "retry_test.txt"], cwd=local_repo, check=True)
        subprocess.run(["git", "commit", "-m", "feat: retry test"], cwd=local_repo, check=True)
        commit_hash = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=local_repo, check=True, capture_output=True, text=True
        ).stdout.strip()

        exec_model = exec_repo.create_execution(
            repo_model.id, "smart", "committed", commit_hash, "feat: retry test"
        )
        exec_repo.update_sync_status(exec_model.id, "PUSH_FAILED", push_error="Simulated network failure")

        from api.routes import get_db
        app.dependency_overrides[get_db] = lambda: test_db
        client = TestClient(app)

        try:
            resp = client.post(f"/api/v1/github/retry/{exec_model.id}")
            assert resp.status_code == 200
            data = resp.json()
            assert data["success"] is True
            assert data["push_sync_status"] == "PUSHED"
        finally:
            app.dependency_overrides.clear()

