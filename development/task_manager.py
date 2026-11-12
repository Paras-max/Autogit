"""
Development Task Manager for AutoGit AI (Phase 3).
Manages user-provided development backlog tasks as well as AI-suggested improvements.
"""

from datetime import datetime, timezone
from typing import List, Optional

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import DevelopmentTaskModel, ProjectContextModel
from utils.logger import logger


class TaskManager:
    """Manages development tasks stored in the SQLite development_tasks table."""

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def add_task(
        self,
        repository_id: int,
        title: str,
        description: Optional[str] = None,
        task_type: str = "feature",
        priority: str = "medium",
    ) -> DevelopmentTaskModel:
        """Add a new task to the repository backlog."""
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO development_tasks (repository_id, title, description, task_type, status, priority, created_at)
                VALUES (?, ?, ?, ?, 'pending', ?, ?)
                """,
                (repository_id, title, description, task_type, priority, now),
            )
            task_id = cursor.lastrowid

        task = DevelopmentTaskModel(
            id=task_id,
            repository_id=repository_id,
            title=title,
            description=description,
            task_type=task_type,
            status="pending",
            priority=priority,
            created_at=now,
        )
        logger.info(f"Added task {task_id} for repo {repository_id}: '{title}' ({task_type})")
        return task

    def get_pending_tasks(self, repository_id: int, limit: int = 10) -> List[DevelopmentTaskModel]:
        """Fetch pending tasks for a repository ordered by priority and creation time."""
        priority_order = "CASE priority WHEN 'high' THEN 1 WHEN 'medium' THEN 2 WHEN 'low' THEN 3 ELSE 4 END"
        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT * FROM development_tasks
                WHERE repository_id = ? AND status = 'pending'
                ORDER BY {priority_order}, id ASC
                LIMIT ?
                """,
                (repository_id, limit),
            )
            rows = cursor.fetchall()
            return [
                DevelopmentTaskModel(
                    id=r["id"],
                    repository_id=r["repository_id"],
                    title=r["title"],
                    description=r["description"],
                    task_type=r["task_type"],
                    status=r["status"],
                    priority=r["priority"],
                    created_at=r["created_at"],
                    completed_at=r["completed_at"],
                )
                for r in rows
            ]

    def get_task(self, task_id: int) -> Optional[DevelopmentTaskModel]:
        """Get task by ID."""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT * FROM development_tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                d = dict(row)
                return DevelopmentTaskModel(
                    id=d["id"],
                    repository_id=d["repository_id"],
                    title=d["title"],
                    description=d["description"],
                    task_type=d["task_type"],
                    status=d["status"],
                    priority=d["priority"],
                    created_at=d["created_at"],
                    completed_at=d.get("completed_at"),
                )
        return None

    def update_task_status(self, task_id: int, status: str) -> bool:
        """Update task status (e.g. 'in_progress', 'completed', 'cancelled')."""
        now = get_utc_now_iso() if status == "completed" else None
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                UPDATE development_tasks
                SET status = ?,
                    completed_at = COALESCE(?, completed_at)
                WHERE id = ?
                """,
                (status, now, task_id),
            )
            return cursor.rowcount > 0

    def suggest_tasks_if_empty(
        self, repository_id: int, context: Optional[ProjectContextModel] = None
    ) -> List[DevelopmentTaskModel]:
        """
        If repository has no pending tasks, generate 2-3 safe, meaningful improvement tasks
        tailored to the project's language and context.
        """
        pending = self.get_pending_tasks(repository_id)
        if pending:
            return pending

        lang = (context.primary_language if context else "python").lower()
        suggested: List[DevelopmentTaskModel] = []

        if lang == "python":
            suggested.append(
                self.add_task(
                    repository_id,
                    title="Add unit tests for core validation helpers",
                    description="Implement test coverage for validator functions to prevent regression.",
                    task_type="test",
                    priority="high",
                )
            )
            suggested.append(
                self.add_task(
                    repository_id,
                    title="Enhance docstrings and type annotations",
                    description="Add PEP 257 docstrings and typing annotations for helper functions.",
                    task_type="documentation",
                    priority="medium",
                )
            )
            suggested.append(
                self.add_task(
                    repository_id,
                    title="Implement input sanitization helper",
                    description="Create reusable input sanitization and trimming helper utility.",
                    task_type="refactor",
                    priority="low",
                )
            )
        else:
            suggested.append(
                self.add_task(
                    repository_id,
                    title="Add utility tests for helper functions",
                    description="Implement unit test cases for helper modules.",
                    task_type="test",
                    priority="high",
                )
            )
            suggested.append(
                self.add_task(
                    repository_id,
                    title="Improve error handling in utility modules",
                    description="Add defensive checks and informative error messages.",
                    task_type="bugfix",
                    priority="medium",
                )
            )

        logger.info(f"Populated {len(suggested)} initial improvement tasks for repo {repository_id}")
        return suggested

