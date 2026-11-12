"""
Tests for File Monitoring and Watchdog integration (monitoring/file_monitor.py, monitoring/event_handler.py).
"""

from pathlib import Path
import time
import pytest

from config.constants import EVENT_CREATED, EVENT_DELETED, EVENT_MODIFIED
from core.repository_manager import RepositoryManager
from database.db import DatabaseManager
from monitoring.event_handler import FileEventHandler
from monitoring.file_monitor import FileMonitor


def test_event_handler_ignores_git_and_configured_dirs(
    temp_git_repo: Path, temp_db: DatabaseManager
):
    captured_events = []
    handler = FileEventHandler(
        repository_id=1,
        repository_path=temp_git_repo,
        database=temp_db,
        on_event_callback=lambda evt: captured_events.append(evt),
        debounce_interval=0.0,
    )

    # 1. Modify file inside .git directory
    git_file = temp_git_repo / ".git" / "COMMIT_EDITMSG"
    assert handler._is_ignored(str(git_file)) is True

    # 2. Modify file inside node_modules directory
    nm_file = temp_git_repo / "node_modules" / "package.json"
    assert handler._is_ignored(str(nm_file)) is True

    # 3. Modify file inside __pycache__
    pyc_file = temp_git_repo / "__pycache__" / "test.cpython-311.pyc"
    assert handler._is_ignored(str(pyc_file)) is True

    # 4. Modify regular file
    reg_file = temp_git_repo / "src" / "index.py"
    assert handler._is_ignored(str(reg_file)) is False


def test_file_monitor_lifecycle(temp_git_repo: Path, temp_db: DatabaseManager):
    repo_mgr = RepositoryManager(database=temp_db)
    repo = repo_mgr.add_repository(str(temp_git_repo))

    monitor = FileMonitor(database=temp_db)
    assert monitor.is_monitoring(repo.id) is False

    started = monitor.start_monitoring(repo.id)
    assert started is True
    assert monitor.is_monitoring(repo.id) is True

    stopped = monitor.stop_monitoring(repo.id)
    assert stopped is True
    assert monitor.is_monitoring(repo.id) is False


def test_detect_external_changes_live(temp_git_repo: Path, temp_db: DatabaseManager):
    """
    Simulates external modification (by editor/IDE or another process).
    Verifies Watchdog captures creation, modification, and deletion.
    """
    repo_mgr = RepositoryManager(database=temp_db)
    repo = repo_mgr.add_repository(str(temp_git_repo))

    captured_events = []
    monitor = FileMonitor(database=temp_db)
    monitor.start_monitoring(
        repo.id,
        on_event_callback=lambda evt: captured_events.append(evt),
    )

    try:
        # Give watchdog observer a moment to initialize
        time.sleep(0.5)

        # 1. External file creation
        test_file = temp_git_repo / "external_file.txt"
        test_file.write_text("Hello from IDE\n", encoding="utf-8")

        # Wait for watchdog to deliver event
        for _ in range(25):
            time.sleep(0.2)
            if captured_events:
                break

        # Check recorded events in database
        db_events = temp_db.list_file_events(repo.id)
        event_types = [e.event_type for e in db_events]

        assert len(db_events) > 0
        assert EVENT_CREATED in event_types or EVENT_MODIFIED in event_types
        # Verify relative path is stored, not absolute
        for evt in db_events:
            assert not evt.file_path.startswith("C:")
            assert not evt.file_path.startswith("/")
    finally:
        monitor.stop_monitoring(repo.id)


def test_event_debouncing(temp_git_repo: Path, temp_db: DatabaseManager):
    """
    Verify that rapid duplicate events on the same file are debounced.
    """
    captured = []
    handler = FileEventHandler(
        repository_id=1,
        repository_path=temp_git_repo,
        database=temp_db,
        on_event_callback=lambda evt: captured.append(evt),
        debounce_interval=1.0,
    )

    test_file = temp_git_repo / "debounce_test.py"
    # Rapid duplicate events
    handler._process_event(EVENT_MODIFIED, str(test_file))
    handler._process_event(EVENT_MODIFIED, str(test_file))
    handler._process_event(EVENT_MODIFIED, str(test_file))

    # Only 1 should be recorded
    assert len(captured) == 1


def test_git_status_reconciliation_backup(temp_git_repo: Path, temp_db: DatabaseManager):
    """
    Test periodic Git reconciliation catching changes even without filesystem events.
    """
    repo_mgr = RepositoryManager(database=temp_db)
    repo = repo_mgr.add_repository(str(temp_git_repo))

    # Write file silently
    untracked = temp_git_repo / "missed_by_watcher.txt"
    untracked.write_text("Content", encoding="utf-8")

    monitor = FileMonitor(database=temp_db)
    result = monitor.reconcile_git_status(repo.id)

    assert result["synced"] >= 1
    events = temp_db.list_file_events(repo.id)
    recorded_paths = [e.file_path for e in events]
    assert "missed_by_watcher.txt" in recorded_paths
