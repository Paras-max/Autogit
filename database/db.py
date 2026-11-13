"""
SQLite database management and operations for AutoGit AI (Phase 1 & Phase 2).
"""

from contextlib import contextmanager
from datetime import datetime, timezone
import json
from pathlib import Path
import sqlite3
from typing import Generator, List, Optional

from config.settings import settings
from database.models import (
    ApplicationServiceStatusModel,
    AuthenticationModel,
    ChangeGroupModel,
    DashboardPreferenceModel,
    DevelopmentChangeModel,
    DevelopmentSessionModel,
    DevelopmentTaskModel,
    ExecutionApprovalModel,
    ExecutionHistoryModel,
    FileEventModel,
    GitHubSyncHistoryModel,
    NotificationModel,
    ProjectContextModel,
    RemoteRepositoryStatusModel,
    RepositoryAutomationSettingsModel,
    RepositoryModel,
    RepositoryPermissionModel,
    ScheduledSessionModel,
    SettingModel,
    ValidationResultModel,
    WeeklyScheduleModel,
)
from utils.logger import logger


SCHEMA_SQL = """
-- Phase 1 Tables
CREATE TABLE IF NOT EXISTS repositories (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_name TEXT NOT NULL,
    repository_path TEXT NOT NULL UNIQUE,
    remote_url TEXT,
    current_branch TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS authentication (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    provider TEXT NOT NULL UNIQUE,
    username TEXT,
    authentication_status TEXT NOT NULL,
    last_validated_at TEXT
);

CREATE TABLE IF NOT EXISTS file_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    event_type TEXT NOT NULL,
    timestamp TEXT DEFAULT (datetime('now')),
    processed_status TEXT DEFAULT 'pending',
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS application_settings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    setting_key TEXT NOT NULL UNIQUE,
    setting_value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_file_events_repo ON file_events(repository_id);
CREATE INDEX IF NOT EXISTS idx_file_events_time ON file_events(timestamp);

-- Phase 2 Tables
CREATE TABLE IF NOT EXISTS execution_history (
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
);

CREATE TABLE IF NOT EXISTS change_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    group_name TEXT NOT NULL,
    explanation TEXT,
    confidence REAL DEFAULT 1.0,
    file_list TEXT NOT NULL DEFAULT '[]',
    FOREIGN KEY (execution_id) REFERENCES execution_history(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS validation_results (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    validation_type TEXT NOT NULL,
    status TEXT NOT NULL,
    output_summary TEXT,
    duration REAL DEFAULT 0.0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (execution_id) REFERENCES execution_history(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS execution_approvals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    execution_id INTEGER NOT NULL,
    approval_status TEXT NOT NULL DEFAULT 'pending',
    approved_at TEXT,
    approved_by TEXT,
    notes TEXT,
    FOREIGN KEY (execution_id) REFERENCES execution_history(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS repository_automation_settings (
    repository_id INTEGER PRIMARY KEY,
    execution_mode TEXT NOT NULL DEFAULT 'smart',
    auto_commit_enabled INTEGER NOT NULL DEFAULT 0,
    push_enabled INTEGER NOT NULL DEFAULT 0,
    protected_branches TEXT NOT NULL DEFAULT '["main", "master"]',
    validation_required INTEGER NOT NULL DEFAULT 1,
    quiet_period_seconds REAL NOT NULL DEFAULT 3.0,
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_exec_history_repo ON execution_history(repository_id);
CREATE INDEX IF NOT EXISTS idx_change_groups_exec ON change_groups(execution_id);
CREATE INDEX IF NOT EXISTS idx_val_results_exec ON validation_results(execution_id);
CREATE INDEX IF NOT EXISTS idx_exec_approvals_exec ON execution_approvals(execution_id);

-- Phase 3 Tables
CREATE TABLE IF NOT EXISTS repository_permissions (
    repository_id INTEGER PRIMARY KEY,
    monitoring_enabled INTEGER NOT NULL DEFAULT 1,
    ai_analysis_enabled INTEGER NOT NULL DEFAULT 1,
    autonomous_development_enabled INTEGER NOT NULL DEFAULT 0,
    smart_commit_enabled INTEGER NOT NULL DEFAULT 1,
    auto_commit_enabled INTEGER NOT NULL DEFAULT 0,
    remote_push_enabled INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS weekly_schedules (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    week_identifier TEXT NOT NULL UNIQUE,
    year INTEGER NOT NULL,
    week_number INTEGER NOT NULL,
    timezone TEXT NOT NULL DEFAULT 'Asia/Kolkata',
    is_active INTEGER NOT NULL DEFAULT 1,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS scheduled_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    schedule_id INTEGER NOT NULL,
    scheduled_date TEXT NOT NULL,
    day_of_week INTEGER NOT NULL,
    time_window TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'scheduled',
    executed_at TEXT,
    notes TEXT,
    FOREIGN KEY (schedule_id) REFERENCES weekly_schedules(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS development_tasks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL,
    title TEXT NOT NULL,
    description TEXT,
    task_type TEXT NOT NULL DEFAULT 'feature',
    status TEXT NOT NULL DEFAULT 'pending',
    priority TEXT NOT NULL DEFAULT 'medium',
    created_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS project_context (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL UNIQUE,
    project_type TEXT NOT NULL,
    primary_language TEXT NOT NULL,
    framework TEXT,
    test_framework TEXT,
    summary TEXT,
    analyzed_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS development_sessions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL,
    session_date TEXT NOT NULL,
    branch_name TEXT NOT NULL,
    worktree_path TEXT,
    status TEXT NOT NULL DEFAULT 'running',
    tasks_summary TEXT,
    files_modified TEXT NOT NULL DEFAULT '[]',
    commit_hash TEXT,
    created_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS development_changes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id INTEGER NOT NULL,
    file_path TEXT NOT NULL,
    change_type TEXT NOT NULL,
    description TEXT,
    diff_snippet TEXT,
    FOREIGN KEY (session_id) REFERENCES development_sessions(id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_sched_sessions_sched ON scheduled_sessions(schedule_id);
CREATE INDEX IF NOT EXISTS idx_sched_sessions_date ON scheduled_sessions(scheduled_date);
CREATE INDEX IF NOT EXISTS idx_dev_tasks_repo ON development_tasks(repository_id);
CREATE INDEX IF NOT EXISTS idx_dev_sessions_repo ON development_sessions(repository_id);
CREATE INDEX IF NOT EXISTS idx_dev_changes_session ON development_changes(session_id);

-- Phase 4 Tables
CREATE TABLE IF NOT EXISTS github_sync_history (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL,
    operation_type TEXT NOT NULL,
    branch TEXT NOT NULL,
    status TEXT NOT NULL,
    commit_hash TEXT,
    started_at TEXT DEFAULT (datetime('now')),
    completed_at TEXT,
    error_summary TEXT,
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS remote_repository_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL UNIQUE,
    local_branch TEXT NOT NULL,
    remote_branch TEXT NOT NULL,
    ahead_count INTEGER NOT NULL DEFAULT 0,
    behind_count INTEGER NOT NULL DEFAULT 0,
    last_fetch_at TEXT,
    last_push_at TEXT,
    sync_status TEXT NOT NULL DEFAULT 'unknown',
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS notifications (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER,
    notification_type TEXT NOT NULL,
    title TEXT NOT NULL,
    message TEXT NOT NULL,
    severity TEXT NOT NULL DEFAULT 'info',
    is_read INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS application_service_status (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    service_name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL,
    last_heartbeat TEXT DEFAULT (datetime('now')),
    last_error TEXT,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS dashboard_preferences (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    preference_key TEXT NOT NULL UNIQUE,
    preference_value TEXT NOT NULL,
    updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pull_requests (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    repository_id INTEGER NOT NULL,
    pr_number INTEGER NOT NULL,
    title TEXT NOT NULL,
    source_branch TEXT NOT NULL,
    target_branch TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'open',
    html_url TEXT NOT NULL,
    is_merged INTEGER NOT NULL DEFAULT 0,
    created_at TEXT DEFAULT (datetime('now')),
    updated_at TEXT DEFAULT (datetime('now')),
    merged_at TEXT,
    body TEXT,
    diff_url TEXT,
    FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE,
    UNIQUE (repository_id, pr_number)
);

CREATE INDEX IF NOT EXISTS idx_sync_hist_repo ON github_sync_history(repository_id);
CREATE INDEX IF NOT EXISTS idx_remote_status_repo ON remote_repository_status(repository_id);
CREATE INDEX IF NOT EXISTS idx_notifications_read ON notifications(is_read);
CREATE INDEX IF NOT EXISTS idx_notifications_time ON notifications(created_at);
CREATE INDEX IF NOT EXISTS idx_pull_requests_repo ON pull_requests(repository_id);
CREATE INDEX IF NOT EXISTS idx_pull_requests_state ON pull_requests(state);
"""


def get_utc_now_iso() -> str:
    """Return timezone-aware current UTC ISO string."""
    return datetime.now(timezone.utc).isoformat()


class DatabaseManager:
    """Manages SQLite database connections and table operations."""

    def __init__(self, db_path: Optional[Path] = None):
        self.db_path = db_path or settings.DATABASE_PATH
        if isinstance(self.db_path, str) and self.db_path != ":memory:":
            self.db_path = Path(self.db_path)
        self._mem_conn = None
        if str(self.db_path) == ":memory:":
            self._mem_conn = sqlite3.connect(":memory:", check_same_thread=False)
            self._mem_conn.row_factory = sqlite3.Row
            self._mem_conn.execute("PRAGMA foreign_keys = ON;")
        self._init_db()

    def _get_connection(self) -> sqlite3.Connection:
        if str(self.db_path) == ":memory:":
            return self._mem_conn
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
        )
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON;")
        return conn

    @contextmanager
    def get_cursor(self) -> Generator[sqlite3.Cursor, None, None]:
        is_mem = str(self.db_path) == ":memory:"
        conn = self._get_connection()
        cursor = conn.cursor()
        if not conn.in_transaction:
            conn.execute("BEGIN")
        try:
            yield cursor
            if conn.in_transaction:
                conn.commit()
        except Exception as e:
            if conn.in_transaction:
                conn.rollback()
            logger.error(f"Database transaction error: {e}")
            raise
        finally:
            cursor.close()
            if not is_mem:
                conn.close()

    def _init_db(self) -> None:
        """Initialize database tables and indexes."""
        try:
            with self.get_cursor() as cursor:
                cursor.executescript(SCHEMA_SQL)
            logger.debug(f"Database initialized at {self.db_path}")
            self._run_migrations()
        except Exception as e:
            logger.error(f"Failed to initialize database: {e}")
            raise

    def _run_migrations(self) -> None:
        """
        Run safe, additive schema migrations inside an explicit transaction.
        Preserves all historical records, foreign keys, and indexes.
        """
        try:
            with self.get_cursor() as cursor:
                # 1. execution_history columns
                cursor.execute("PRAGMA table_info(execution_history)")
                existing_cols = {row["name"] for row in cursor.fetchall()}

                new_columns = [
                    ("push_sync_status", "TEXT DEFAULT 'UNKNOWN'"),
                    ("branch_name", "TEXT"),
                    ("local_commit_hash", "TEXT"),
                    ("remote_commit_hash", "TEXT"),
                    ("remote_advanced", "INTEGER NOT NULL DEFAULT 0"),
                    ("verification_status", "TEXT"),
                    ("source_branch", "TEXT"),
                    ("target_branch", "TEXT"),
                    ("remote_name", "TEXT"),
                    ("push_timestamp", "TEXT"),
                    ("push_error", "TEXT"),
                ]

                for col_name, col_type in new_columns:
                    if col_name not in existing_cols:
                        cursor.execute(
                            f"ALTER TABLE execution_history ADD COLUMN {col_name} {col_type}"
                        )
                        logger.info(f"Migration: added {col_name} to execution_history")

                # 2. pull_requests table (no hardcoded target_branch default)
                cursor.execute(
                    """
                    CREATE TABLE IF NOT EXISTS pull_requests (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        repository_id INTEGER NOT NULL,
                        pr_number INTEGER NOT NULL,
                        title TEXT NOT NULL,
                        source_branch TEXT NOT NULL,
                        target_branch TEXT NOT NULL,
                        state TEXT NOT NULL DEFAULT 'open',
                        html_url TEXT NOT NULL,
                        is_merged INTEGER NOT NULL DEFAULT 0,
                        created_at TEXT DEFAULT (datetime('now')),
                        updated_at TEXT DEFAULT (datetime('now')),
                        merged_at TEXT,
                        body TEXT,
                        diff_url TEXT,
                        FOREIGN KEY (repository_id) REFERENCES repositories(id) ON DELETE CASCADE,
                        UNIQUE (repository_id, pr_number)
                    )
                    """
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pull_requests_repo ON pull_requests(repository_id)"
                )
                cursor.execute(
                    "CREATE INDEX IF NOT EXISTS idx_pull_requests_state ON pull_requests(state)"
                )
        except Exception as e:
            logger.error(f"Migration error: {e}")
            raise

    # =========================================================================
    # Phase 1 Methods
    # =========================================================================

    def add_repository(
        self,
        name: str,
        path: str,
        remote_url: Optional[str] = None,
        current_branch: Optional[str] = None,
    ) -> RepositoryModel:
        now = get_utc_now_iso()
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO repositories (repository_name, repository_path, remote_url, current_branch, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (name, str(Path(path).resolve()), remote_url, current_branch, now),
            )
            repo_id = cursor.lastrowid
            cursor.execute(
                """
                INSERT OR IGNORE INTO repository_permissions (repository_id, monitoring_enabled, ai_analysis_enabled, autonomous_development_enabled, smart_commit_enabled, auto_commit_enabled, remote_push_enabled, updated_at)
                VALUES (?, 1, 1, 0, 1, 0, 0, ?)
                """,
                (repo_id, now),
            )
        return RepositoryModel(
            id=repo_id,
            repository_name=name,
            repository_path=str(Path(path).resolve()),
            remote_url=remote_url,
            current_branch=current_branch,
            created_at=now,
        )

    def get_repository(self, repo_id: int) -> Optional[RepositoryModel]:
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM repositories WHERE id = ?", (repo_id,))
            row = cursor.fetchone()
            if row:
                return RepositoryModel(**dict(row))
        return None

    def get_repository_by_path(self, path: str) -> Optional[RepositoryModel]:
        resolved = str(Path(path).resolve())
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM repositories WHERE repository_path = ?", (resolved,))
            row = cursor.fetchone()
            if row:
                return RepositoryModel(**dict(row))
        return None

    def list_repositories(self) -> List[RepositoryModel]:
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM repositories ORDER BY id ASC")
            rows = cursor.fetchall()
            return [RepositoryModel(**dict(r)) for r in rows]

    def update_repository(
        self,
        repo_id: int,
        remote_url: Optional[str] = None,
        current_branch: Optional[str] = None,
    ) -> Optional[RepositoryModel]:
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE repositories
                SET remote_url = COALESCE(?, remote_url),
                    current_branch = COALESCE(?, current_branch)
                WHERE id = ?
                """,
                (remote_url, current_branch, repo_id),
            )
        return self.get_repository(repo_id)

    def remove_repository(self, repo_id: int) -> bool:
        with self.get_cursor() as cursor:
            cursor.execute("DELETE FROM repositories WHERE id = ?", (repo_id,))
            return cursor.rowcount > 0

    def upsert_authentication(
        self,
        provider: str,
        authentication_status: str,
        username: Optional[str] = None,
    ) -> AuthenticationModel:
        now = get_utc_now_iso()
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO authentication (provider, username, authentication_status, last_validated_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(provider) DO UPDATE SET
                    username = excluded.username,
                    authentication_status = excluded.authentication_status,
                    last_validated_at = excluded.last_validated_at
                """,
                (provider, username, authentication_status, now),
            )
            cursor.execute("SELECT * FROM authentication WHERE provider = ?", (provider,))
            row = cursor.fetchone()
            return AuthenticationModel(**dict(row))

    def get_authentication(self, provider: str) -> Optional[AuthenticationModel]:
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM authentication WHERE provider = ?", (provider,))
            row = cursor.fetchone()
            if row:
                return AuthenticationModel(**dict(row))
        return None

    def list_authentications(self) -> List[AuthenticationModel]:
        with self.get_cursor() as cursor:
            cursor.execute("SELECT * FROM authentication ORDER BY provider ASC")
            rows = cursor.fetchall()
            return [AuthenticationModel(**dict(r)) for r in rows]

    def add_file_event(
        self,
        repository_id: int,
        file_path: str,
        event_type: str,
        timestamp: Optional[str] = None,
        processed_status: str = "pending",
    ) -> FileEventModel:
        ts = timestamp or get_utc_now_iso()
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO file_events (repository_id, file_path, event_type, timestamp, processed_status)
                VALUES (?, ?, ?, ?, ?)
                """,
                (repository_id, file_path, event_type, ts, processed_status),
            )
            event_id = cursor.lastrowid
        return FileEventModel(
            id=event_id,
            repository_id=repository_id,
            file_path=file_path,
            event_type=event_type,
            timestamp=ts,
            processed_status=processed_status,
        )

    def list_file_events(
        self, repository_id: int, limit: int = 100
    ) -> List[FileEventModel]:
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                SELECT * FROM file_events
                WHERE repository_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (repository_id, limit),
            )
            rows = cursor.fetchall()
            return [FileEventModel(**dict(r)) for r in rows]

    def set_setting(self, key: str, value: str) -> SettingModel:
        now = get_utc_now_iso()
        with self.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO application_settings (setting_key, setting_value, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(setting_key) DO UPDATE SET
                    setting_value = excluded.setting_value,
                    updated_at = excluded.updated_at
                """,
                (key, value, now),
            )
            cursor.execute("SELECT * FROM application_settings WHERE setting_key = ?", (key,))
            row = cursor.fetchone()
            return SettingModel(**dict(row))

    def get_setting(self, key: str) -> Optional[SettingModel]:
        with self.get_cursor() as cursor:
            cursor.execute(
                "SELECT * FROM application_settings WHERE setting_key = ?", (key,)
            )
            row = cursor.fetchone()
            if row:
                return SettingModel(**dict(row))
        return None


# Global default database instance
db = DatabaseManager()
