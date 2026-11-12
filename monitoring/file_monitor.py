"""
File Monitor module using Watchdog and background Git status reconciliation.
Runs independently of IDEs to detect changes made anywhere in the repository.
Includes quiet period aggregation for intelligent pipeline triggering.
"""

from datetime import datetime, timezone
from pathlib import Path
import threading
import time
from typing import Any, Callable, Dict, List, Optional
from watchdog.observers import Observer

from config.constants import (
    EVENT_CREATED,
    EVENT_DELETED,
    EVENT_MODIFIED,
    EVENT_MOVED,
)
from config.settings import settings
from core.git_manager import GitManager
from database.db import DatabaseManager, db as default_db
from database.models import FileEventModel
from monitoring.event_handler import FileEventHandler
from utils.logger import logger


class FileMonitor:
    """
    Manages filesystem monitoring observers, quiet periods, and periodic Git reconciliation
    across registered repositories.
    """

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        on_quiet_pipeline_callback: Optional[Callable[[int], None]] = None,
    ):
        self.db = database or default_db
        # Map repository_id -> Observer
        self._observers: Dict[int, Observer] = {}
        # Map repository_id -> FileEventHandler
        self._handlers: Dict[int, FileEventHandler] = {}
        # Quiet period timers map
        self._quiet_timers: Dict[int, threading.Timer] = {}
        self.on_quiet_pipeline_callback = on_quiet_pipeline_callback
        # Reconciliation thread control
        self._reconciliation_thread: Optional[threading.Thread] = None
        self._reconciliation_running = threading.Event()
        self._reconciliation_interval = settings.GIT_RECONCILIATION_INTERVAL_SECONDS
        self._lock = threading.Lock()

    def _on_file_event_captured(
        self, repository_id: int, event_model: FileEventModel, user_callback: Optional[Callable]
    ):
        if user_callback:
            try:
                user_callback(event_model)
            except Exception as e:
                logger.error(f"Error in user event callback: {e}")

        # Reset quiet period timer
        with self._lock:
            existing_timer = self._quiet_timers.pop(repository_id, None)
            if existing_timer:
                existing_timer.cancel()

            # Schedule pipeline invocation after quiet period if configured
            if self.on_quiet_pipeline_callback:
                t = threading.Timer(
                    settings.DEBOUNCE_INTERVAL_SECONDS * 2.0,
                    self._on_quiet_elapsed,
                    args=[repository_id],
                )
                t.daemon = True
                t.start()
                self._quiet_timers[repository_id] = t

    def _on_quiet_elapsed(self, repository_id: int):
        logger.info(f"Quiet period elapsed for repository ID {repository_id}. Triggering pipeline reconciliation.")
        self.reconcile_git_status(repository_id)
        if self.on_quiet_pipeline_callback:
            try:
                self.on_quiet_pipeline_callback(repository_id)
            except Exception as e:
                logger.error(f"Error in on_quiet_pipeline_callback: {e}")

    def start_monitoring(
        self,
        repository_id: int,
        on_event_callback: Optional[Callable[[FileEventModel], None]] = None,
        ignored_patterns: Optional[List[str]] = None,
    ) -> bool:
        with self._lock:
            if repository_id in self._observers and self._observers[repository_id].is_alive():
                logger.info(f"Repository {repository_id} is already actively monitored.")
                return True

            repo = self.db.get_repository(repository_id)
            if not repo:
                logger.error(f"Cannot monitor repository: ID {repository_id} not found in database.")
                return False

            repo_path = Path(repo.repository_path)
            if not repo_path.exists():
                logger.error(f"Repository path does not exist on disk: {repo_path}")
                return False

            # Wrap callback with quiet period tracker
            handler = FileEventHandler(
                repository_id=repository_id,
                repository_path=repo_path,
                database=self.db,
                on_event_callback=lambda evt: self._on_file_event_captured(
                    repository_id, evt, on_event_callback
                ),
                ignored_patterns=ignored_patterns,
                debounce_interval=settings.DEBOUNCE_INTERVAL_SECONDS,
            )

            observer = Observer()
            observer.schedule(handler, str(repo_path), recursive=True)
            observer.daemon = True
            observer.start()

            self._observers[repository_id] = observer
            self._handlers[repository_id] = handler

            logger.info(
                f"Started file monitoring for repository '{repo.repository_name}' (ID: {repository_id}) at {repo_path}"
            )

            self._ensure_reconciliation_thread()
            return True

    def stop_monitoring(self, repository_id: int) -> bool:
        with self._lock:
            timer = self._quiet_timers.pop(repository_id, None)
            if timer:
                timer.cancel()

            observer = self._observers.pop(repository_id, None)
            self._handlers.pop(repository_id, None)

            if observer:
                try:
                    observer.stop()
                    observer.join(timeout=2.0)
                    logger.info(f"Stopped file monitoring for repository ID {repository_id}")
                    return True
                except Exception as e:
                    logger.error(f"Error stopping observer for repository ID {repository_id}: {e}")
                    return False

            logger.warning(f"No active monitor found for repository ID {repository_id}")
            return False

    def is_monitoring(self, repository_id: int) -> bool:
        with self._lock:
            observer = self._observers.get(repository_id)
            return bool(observer and observer.is_alive())

    def get_status(self, repository_id: int) -> Dict[str, Any]:
        is_active = self.is_monitoring(repository_id)
        repo = self.db.get_repository(repository_id)
        return {
            "repository_id": repository_id,
            "repository_name": repo.repository_name if repo else "unknown",
            "is_active": is_active,
            "reconciliation_running": self._reconciliation_running.is_set(),
        }

    def stop_all(self) -> None:
        with self._lock:
            for timer in self._quiet_timers.values():
                timer.cancel()
            self._quiet_timers.clear()

            for repo_id, observer in list(self._observers.items()):
                try:
                    observer.stop()
                    observer.join(timeout=1.0)
                except Exception as e:
                    logger.error(f"Error stopping observer {repo_id}: {e}")
            self._observers.clear()
            self._handlers.clear()

            if self._reconciliation_running.is_set():
                self._reconciliation_running.clear()
                if self._reconciliation_thread and self._reconciliation_thread.is_alive():
                    self._reconciliation_thread.join(timeout=2.0)
                self._reconciliation_thread = None

            logger.info("All file monitors and reconciliation threads stopped.")

    def on_file_created(self, repository_id: int, file_path: str):
        handler = self._handlers.get(repository_id)
        if handler:
            handler._process_event(EVENT_CREATED, file_path)

    def on_file_modified(self, repository_id: int, file_path: str):
        handler = self._handlers.get(repository_id)
        if handler:
            handler._process_event(EVENT_MODIFIED, file_path)

    def on_file_deleted(self, repository_id: int, file_path: str):
        handler = self._handlers.get(repository_id)
        if handler:
            handler._process_event(EVENT_DELETED, file_path)

    def on_file_moved(self, repository_id: int, src_path: str, dest_path: str):
        handler = self._handlers.get(repository_id)
        if handler:
            handler._process_event(EVENT_MOVED, src_path, dest_path)

    def reconcile_git_status(self, repository_id: int) -> Dict[str, int]:
        repo = self.db.get_repository(repository_id)
        if not repo:
            return {"synced": 0}

        try:
            git_mgr = GitManager(repo.repository_path)
            changes = git_mgr.get_file_changes()
            existing_events = self.db.list_file_events(repository_id, limit=50)
            existing_paths = {e.file_path for e in existing_events if e.processed_status == "pending"}

            synced_count = 0
            now = datetime.now(timezone.utc).isoformat()

            for item in changes.get("untracked", []):
                if item not in existing_paths:
                    self.db.add_file_event(repository_id, item, EVENT_CREATED, now)
                    synced_count += 1

            for item in changes.get("modified", []):
                if item not in existing_paths:
                    self.db.add_file_event(repository_id, item, EVENT_MODIFIED, now)
                    synced_count += 1

            for item in changes.get("deleted", []):
                if item not in existing_paths:
                    self.db.add_file_event(repository_id, item, EVENT_DELETED, now)
                    synced_count += 1

            if synced_count > 0:
                logger.info(
                    f"Git reconciliation synchronized {synced_count} pending changes for repo ID {repository_id}"
                )
            return {"synced": synced_count}
        except Exception as e:
            logger.debug(f"Git reconciliation check error for repo ID {repository_id}: {e}")
            return {"synced": 0}

    def _ensure_reconciliation_thread(self) -> None:
        if not self._reconciliation_running.is_set():
            self._reconciliation_running.set()
            self._reconciliation_thread = threading.Thread(
                target=self._reconciliation_loop,
                daemon=True,
                name="GitReconciliationWorker",
            )
            self._reconciliation_thread.start()

    def _reconciliation_loop(self) -> None:
        while self._reconciliation_running.is_set():
            time.sleep(self._reconciliation_interval)
            active_ids = list(self._observers.keys())
            for repo_id in active_ids:
                if not self._reconciliation_running.is_set():
                    break
                self.reconcile_git_status(repo_id)


# Global default monitor instance
file_monitor = FileMonitor()
