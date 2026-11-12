"""
Watchdog event handler with debouncing and pattern filtering for AutoGit AI.
"""

from datetime import datetime, timezone
import fnmatch
import os
from pathlib import Path
import time
from typing import Callable, Dict, List, Optional, Set, Tuple
from watchdog.events import (
    FileCreatedEvent,
    FileDeletedEvent,
    FileModifiedEvent,
    FileMovedEvent,
    FileSystemEvent,
    FileSystemEventHandler,
)

from config.constants import (
    DEFAULT_IGNORED_DIRS,
    DEFAULT_IGNORED_EXTENSIONS,
    EVENT_CREATED,
    EVENT_DELETED,
    EVENT_MODIFIED,
    EVENT_MOVED,
)
from database.db import DatabaseManager, db as default_db
from database.models import FileEventModel
from utils.logger import logger


class FileEventHandler(FileSystemEventHandler):
    """
    Handles filesystem events for a specific repository.
    Includes debouncing to prevent multiple notifications on single editor saves,
    and filters out ignored paths and directories.
    """

    def __init__(
        self,
        repository_id: int,
        repository_path: Path,
        database: Optional[DatabaseManager] = None,
        on_event_callback: Optional[Callable[[FileEventModel], None]] = None,
        ignored_dirs: Optional[Set[str]] = None,
        ignored_patterns: Optional[List[str]] = None,
        debounce_interval: float = 1.0,
    ):
        super().__init__()
        self.repository_id = repository_id
        self.repository_path = Path(repository_path).resolve()
        self.db = database or default_db
        self.on_event_callback = on_event_callback
        self.ignored_dirs = ignored_dirs or DEFAULT_IGNORED_DIRS
        self.ignored_patterns = ignored_patterns or []
        self.debounce_interval = debounce_interval

        # Cache for debouncing: key is (relative_path, event_type) -> last_event_time
        self._last_event_timestamps: Dict[Tuple[str, str], float] = {}

    def _is_ignored(self, file_path_str: str) -> bool:
        """
        Determine whether a given file path should be ignored.
        Checks directory parts, file extensions, and custom patterns.
        """
        try:
            abs_file = os.path.abspath(file_path_str)
            abs_repo = os.path.abspath(self.repository_path)
            rel = os.path.relpath(abs_file, abs_repo)
            if rel.startswith(".."):
                return True
            rel_path = Path(rel)
        except Exception:
            return True

        # Check path parts against ignored directories (.git, node_modules, etc.)
        for part in rel_path.parts:
            if part in self.ignored_dirs:
                return True

        # Check ignored file extensions (.pyc, .tmp, etc.)
        if rel_path.suffix.lower() in DEFAULT_IGNORED_EXTENSIONS:
            return True

        # Check custom patterns
        rel_str = rel_path.as_posix()
        for pattern in self.ignored_patterns:
            if fnmatch.fnmatch(rel_str, pattern):
                return True

        return False

    def _get_relative_path(self, absolute_path_str: str) -> str:
        """Convert absolute path to relative path with forward slashes."""
        try:
            abs_file = os.path.abspath(absolute_path_str)
            abs_repo = os.path.abspath(self.repository_path)
            rel = os.path.relpath(abs_file, abs_repo)
            return Path(rel).as_posix()
        except Exception:
            return Path(absolute_path_str).name

    def _should_debounce(self, rel_path: str, event_type: str) -> bool:
        """
        Check if event is a rapid duplicate of a recent event within debounce_interval.
        """
        key = (rel_path, event_type)
        now = time.time()
        last_time = self._last_event_timestamps.get(key, 0)
        if (now - last_time) < self.debounce_interval:
            return True

        self._last_event_timestamps[key] = now
        return False

    def _process_event(self, event_type: str, src_path: str, dest_path: Optional[str] = None):
        """Common processor for handling, debouncing, recording, and broadcasting an event."""
        if self._is_ignored(src_path):
            return

        rel_path = self._get_relative_path(src_path)
        if dest_path:
            rel_dest = self._get_relative_path(dest_path)
            rel_path = f"{rel_path} -> {rel_dest}"

        if self._should_debounce(rel_path, event_type):
            return

        now_iso = datetime.now(timezone.utc).isoformat()
        logger.info(
            f"[Watcher Repo {self.repository_id}] {event_type}: {rel_path}"
        )

        # Store in SQLite
        try:
            event_model = self.db.add_file_event(
                repository_id=self.repository_id,
                file_path=rel_path,
                event_type=event_type,
                timestamp=now_iso,
                processed_status="pending",
            )
        except Exception as e:
            logger.error(f"Failed to record file event in database: {e}")
            event_model = FileEventModel(
                id=None,
                repository_id=self.repository_id,
                file_path=rel_path,
                event_type=event_type,
                timestamp=now_iso,
                processed_status="pending",
            )

        # Trigger callback if registered
        if self.on_event_callback:
            try:
                self.on_event_callback(event_model)
            except Exception as e:
                logger.error(f"Error in on_event_callback: {e}")

    # Watchdog Handlers
    def on_created(self, event: FileSystemEvent):
        if not event.is_directory:
            self._process_event(EVENT_CREATED, event.src_path)

    def on_modified(self, event: FileSystemEvent):
        if not event.is_directory:
            self._process_event(EVENT_MODIFIED, event.src_path)

    def on_deleted(self, event: FileSystemEvent):
        if not event.is_directory:
            self._process_event(EVENT_DELETED, event.src_path)

    def on_moved(self, event: FileMovedEvent):
        if not event.is_directory:
            self._process_event(EVENT_MOVED, event.src_path, event.dest_path)
