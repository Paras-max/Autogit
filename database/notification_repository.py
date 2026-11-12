"""
Notification repository for Phase 4 database access: in-app notifications.
"""

from typing import List, Optional

from database.db import DatabaseManager, db as default_db, get_utc_now_iso
from database.models import NotificationModel
from utils.logger import logger


class NotificationRepository:
    """Manages notifications in SQLite."""

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    def create_notification(
        self,
        notification_type: str,
        title: str,
        message: str,
        repository_id: Optional[int] = None,
        severity: str = "info",
    ) -> NotificationModel:
        """Create and persist a new notification."""
        now = get_utc_now_iso()
        with self.db.get_cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO notifications (
                    repository_id, notification_type, title, message, severity, is_read, created_at
                ) VALUES (?, ?, ?, ?, ?, 0, ?)
                """,
                (repository_id, notification_type, title, message, severity, now),
            )
            notif_id = cursor.lastrowid

        return NotificationModel(
            id=notif_id,
            repository_id=repository_id,
            notification_type=notification_type,
            title=title,
            message=message,
            severity=severity,
            is_read=False,
            created_at=now,
        )

    def list_notifications(
        self, limit: int = 50, unread_only: bool = False
    ) -> List[NotificationModel]:
        """Fetch recent notifications."""
        where_clause = "WHERE is_read = 0" if unread_only else ""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                f"""
                SELECT * FROM notifications
                {where_clause}
                ORDER BY id DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
            return [
                NotificationModel(
                    id=r["id"],
                    repository_id=r["repository_id"],
                    notification_type=r["notification_type"],
                    title=r["title"],
                    message=r["message"],
                    severity=r["severity"],
                    is_read=bool(r["is_read"]),
                    created_at=r["created_at"],
                )
                for r in rows
            ]

    def mark_read(self, notification_id: int) -> bool:
        """Mark a single notification as read."""
        with self.db.get_cursor() as cursor:
            cursor.execute(
                "UPDATE notifications SET is_read = 1 WHERE id = ?",
                (notification_id,),
            )
            return cursor.rowcount > 0

    def mark_all_read(self) -> int:
        """Mark all notifications as read."""
        with self.db.get_cursor() as cursor:
            cursor.execute("UPDATE notifications SET is_read = 1 WHERE is_read = 0")
            return cursor.rowcount

    def get_unread_count(self) -> int:
        """Get the count of unread notifications."""
        with self.db.get_cursor() as cursor:
            cursor.execute("SELECT COUNT(*) as cnt FROM notifications WHERE is_read = 0")
            row = cursor.fetchone()
            return row["cnt"] if row else 0

