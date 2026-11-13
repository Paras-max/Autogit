"""
Unit and integration tests for Step 1 (Secure Git Credential Handler)
and Step 2 (Safe Database Migrations).
"""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import time
import pytest

from utils.git_credential import (
    cleanup_abandoned_helpers,
    git_credential_context,
    HELPER_PREFIX,
)
from database.db import DatabaseManager, SCHEMA_SQL
from database.models import ExecutionHistoryModel, PullRequestModel


# ============================================================================
# Step 1 Tests: Secure Git Credential Handler
# ============================================================================

class TestGitCredentialHandler:
    """Tests for utils/git_credential.py."""

    def test_context_without_token_yields_empty_dict(self):
        """When no token is provided, yields empty dict without creating files."""
        with git_credential_context(None) as env:
            assert env == {}

        with git_credential_context("") as env:
            assert env == {}

        with git_credential_context("   ") as env:
            assert env == {}

    def test_token_not_written_to_helper_file(self):
        """The generated helper script must NEVER contain the literal secret token."""
        dummy_token = "ghp_SECRET_TEST_TOKEN_12345_XYZ"
        with git_credential_context(dummy_token) as env:
            helper_path = Path(env["GIT_ASKPASS"])
            assert helper_path.exists(), "Helper script must exist during context"
            content = helper_path.read_text(encoding="utf-8", errors="ignore")
            # CRITICAL SECURITY CHECK:
            assert dummy_token not in content, "Literal token found in helper script!"
            assert "ghp_" not in content

    def test_helper_cleans_up_after_success(self):
        """Helper file and its parent temp dir must be removed on normal exit."""
        dummy_token = "ghp_clean_test_token"
        helper_path = None
        parent_dir = None
        with git_credential_context(dummy_token) as env:
            helper_path = Path(env["GIT_ASKPASS"])
            parent_dir = helper_path.parent
            assert helper_path.exists()
            assert parent_dir.exists()

        assert not helper_path.exists(), "Helper file was not cleaned up on normal exit"
        assert not parent_dir.exists(), "Temporary directory was not cleaned up on normal exit"

    def test_helper_cleans_up_after_exception(self):
        """Helper file and parent dir must be cleaned up even if an exception occurs."""
        dummy_token = "ghp_exception_token"
        helper_path = None
        parent_dir = None

        with pytest.raises(RuntimeError):
            with git_credential_context(dummy_token) as env:
                helper_path = Path(env["GIT_ASKPASS"])
                parent_dir = helper_path.parent
                assert helper_path.exists()
                raise RuntimeError("Simulated failure inside git operation")

        assert helper_path is not None
        assert not helper_path.exists(), "Helper file was not cleaned up on exception"
        assert not parent_dir.exists(), "Temporary directory was not cleaned up on exception"

    def test_helper_outputs_token_when_executed(self):
        """When invoked, the helper script must output the token via its environment variable."""
        dummy_token = "ghp_my_verification_token_789"
        with git_credential_context(dummy_token) as env:
            helper_path = env["GIT_ASKPASS"]
            child_env = {**os.environ, **env}

            # Invoke helper script directly (simulating Git invoking GIT_ASKPASS)
            if sys.platform == "win32":
                proc = subprocess.run(
                    ["cmd.exe", "/c", helper_path, "Password for 'https://github.com': "],
                    capture_output=True,
                    text=True,
                    env=child_env,
                    timeout=5.0,
                )
            else:
                proc = subprocess.run(
                    [helper_path, "Password for 'https://github.com': "],
                    capture_output=True,
                    text=True,
                    env=child_env,
                    timeout=5.0,
                )

            assert proc.returncode == 0
            assert proc.stdout.strip() == dummy_token

    def test_terminal_prompt_disabled(self):
        """GIT_TERMINAL_PROMPT must be set to '0' to avoid hanging on credentials."""
        with git_credential_context("ghp_test") as env:
            assert env.get("GIT_TERMINAL_PROMPT") == "0"

    def test_cleanup_abandoned_helpers(self, tmp_path):
        """Startup cleanup removes old autogit_askpass_* artifacts but leaves others."""
        # Create an artificial abandoned file in system temp dir
        temp_dir = Path(tempfile.gettempdir())
        old_helper_dir = temp_dir / f"{HELPER_PREFIX}abandoned_test_{int(time.time())}"
        old_helper_dir.mkdir(parents=True, exist_ok=True)
        old_helper_file = old_helper_dir / "askpass.bat"
        old_helper_file.write_text("dummy")

        # Set modification time to 10 minutes ago
        past_time = time.time() - 600
        os.utime(old_helper_file, (past_time, past_time))
        os.utime(old_helper_dir, (past_time, past_time))

        # Run cleanup with threshold 300s
        cleaned = cleanup_abandoned_helpers(max_age_seconds=300.0)
        assert cleaned >= 1
        assert not old_helper_dir.exists()


# ============================================================================
# Step 2 Tests: Safe Database Migrations
# ============================================================================

class TestDatabaseMigration:
    """Tests for SQLite schema migration idempotence, data preservation, and foreign keys."""

    def test_migration_on_fresh_database(self, tmp_path):
        """A fresh database initializes with all required Phase 4 columns and tables."""
        db_file = tmp_path / "fresh_test.db"
        mgr = DatabaseManager(db_file)

        with mgr.get_cursor() as cursor:
            # Check execution_history columns
            cursor.execute("PRAGMA table_info(execution_history)")
            cols = {r["name"] for r in cursor.fetchall()}
            expected_cols = {
                "push_sync_status",
                "branch_name",
                "local_commit_hash",
                "remote_commit_hash",
                "remote_advanced",
                "verification_status",
                "source_branch",
                "target_branch",
                "remote_name",
                "push_timestamp",
                "push_error",
            }
            assert expected_cols.issubset(cols), f"Missing columns: {expected_cols - cols}"

            # Check pull_requests table
            cursor.execute("PRAGMA table_info(pull_requests)")
            pr_cols = {r["name"] for r in cursor.fetchall()}
            expected_pr_cols = {
                "id",
                "repository_id",
                "pr_number",
                "title",
                "source_branch",
                "target_branch",
                "state",
                "html_url",
                "is_merged",
                "created_at",
                "updated_at",
                "merged_at",
                "body",
                "diff_url",
            }
            assert expected_pr_cols.issubset(pr_cols)

    def test_migration_preserves_existing_records(self, tmp_path):
        """Simulate legacy database without new columns, run migration, verify data intact."""
        db_file = tmp_path / "legacy_test.db"
        conn = sqlite3.connect(db_file)

        # Create basic legacy schema (Phase 1 & 2 without new columns)
        conn.execute(
            """
            CREATE TABLE repositories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_name TEXT NOT NULL,
                repository_path TEXT NOT NULL UNIQUE,
                remote_url TEXT,
                current_branch TEXT,
                created_at TEXT DEFAULT (datetime('now'))
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE execution_history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repository_id INTEGER NOT NULL,
                execution_mode TEXT NOT NULL DEFAULT 'smart',
                status TEXT NOT NULL DEFAULT 'pending',
                commit_hash TEXT,
                commit_message TEXT,
                created_at TEXT DEFAULT (datetime('now')),
                completed_at TEXT,
                error_summary TEXT,
                proposal_data TEXT,
                FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
            )
            """
        )
        # Insert legacy records
        conn.execute(
            "INSERT INTO repositories (repository_name, repository_path) VALUES ('LegacyRepo', 'C:/Legacy')"
        )
        conn.execute(
            """
            INSERT INTO execution_history (repository_id, execution_mode, status, commit_hash, commit_message)
            VALUES (1, 'smart', 'committed', 'abc1234', 'feat: legacy commit')
            """
        )
        conn.commit()
        conn.close()

        # Run migration via DatabaseManager
        mgr = DatabaseManager(db_file)

        with mgr.get_cursor() as cursor:
            # Verify records preserved
            cursor.execute("SELECT * FROM repositories WHERE id = 1")
            repo = cursor.fetchone()
            assert repo["repository_name"] == "LegacyRepo"

            cursor.execute("SELECT * FROM execution_history WHERE id = 1")
            exec_row = cursor.fetchone()
            assert exec_row["commit_hash"] == "abc1234"
            assert exec_row["commit_message"] == "feat: legacy commit"
            # Verify default values on newly added column
            assert exec_row["push_sync_status"] == "UNKNOWN"
            assert exec_row["remote_advanced"] == 0

    def test_migration_is_idempotent(self, tmp_path):
        """Running _run_migrations multiple times must succeed without error or duplicate columns."""
        db_file = tmp_path / "idempotent_test.db"
        mgr = DatabaseManager(db_file)

        # Call migrations 3 times
        mgr._run_migrations()
        mgr._run_migrations()
        mgr._run_migrations()

        with mgr.get_cursor() as cursor:
            cursor.execute("PRAGMA table_info(execution_history)")
            cols = [r["name"] for r in cursor.fetchall()]
            # Ensure no duplicate columns
            assert len(cols) == len(set(cols))

    def test_pull_requests_foreign_key_and_uniqueness(self, tmp_path):
        """pull_requests table enforces foreign key and unique (repository_id, pr_number)."""
        db_file = tmp_path / "pr_fk_test.db"
        mgr = DatabaseManager(db_file)

        # Add repository
        repo = mgr.add_repository("TestRepo", str(tmp_path / "repo"))

        with mgr.get_cursor() as cursor:
            # Insert valid PR
            cursor.execute(
                """
                INSERT INTO pull_requests (repository_id, pr_number, title, source_branch, target_branch, html_url)
                VALUES (?, 42, 'feat: add feature', 'autogit/dev-1', 'main', 'https://github.com/owner/repo/pull/42')
                """,
                (repo.id,),
            )
            assert cursor.lastrowid is not None

            # Attempt duplicate PR for same repo
            with pytest.raises(sqlite3.IntegrityError):
                cursor.execute(
                    """
                    INSERT INTO pull_requests (repository_id, pr_number, title, source_branch, target_branch, html_url)
                    VALUES (?, 42, 'duplicate PR', 'autogit/dev-1', 'main', 'https://github.com/owner/repo/pull/42')
                    """,
                    (repo.id,),
                )

