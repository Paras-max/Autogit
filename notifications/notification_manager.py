"""
Notification Manager for AutoGit AI (Phase 4).
Handles creating, fetching, reading, and clearing user notifications.
Connects with Desktop Notifications and Event Dispatcher.
"""

from typing import Any, Dict, List, Optional

from database.db import DatabaseManager, db as default_db
from database.models import NotificationModel
from database.notification_repository import NotificationRepository
from notifications.desktop_notifications import send_desktop_notification
from notifications.event_dispatcher import event_dispatcher
from utils.logger import logger


class NotificationManager:
    """Coordinates persistent database notifications, desktop alerts, and live event broadcasts."""

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        notif_repo: Optional[NotificationRepository] = None,
    ):
        self.db = database or default_db
        self.notif_repo = notif_repo or NotificationRepository(self.db)

    def notify(
        self,
        notification_type: str,
        title: str,
        message: str,
        repository_id: Optional[int] = None,
        severity: str = "info",
        notify_desktop: bool = True,
    ) -> NotificationModel:
        """
        Record a notification in SQLite, broadcast live event, and optionally send desktop alert.
        """
        notif = self.notif_repo.create_notification(
            notification_type=notification_type,
            title=title,
            message=message,
            repository_id=repository_id,
            severity=severity,
        )

        # Broadcast through live event dispatcher
        event_dispatcher.dispatch(
            event_type="notification_created",
            data={
                "id": notif.id,
                "title": notif.title,
                "message": notif.message,
                "severity": notif.severity,
                "type": notif.notification_type,
            },
            repository_id=repository_id,
        )

        # Trigger desktop alert for notable severities
        if notify_desktop and severity in ("warning", "error", "success"):
            send_desktop_notification(title, message, severity)

        logger.info(f"Notification [{severity.upper()}] {title}: {message[:60]}")
        return notif

    def list_notifications(
        self, limit: int = 50, unread_only: bool = False
    ) -> List[NotificationModel]:
        return self.notif_repo.list_notifications(limit=limit, unread_only=unread_only)

    def mark_as_read(self, notification_id: int) -> bool:
        res = self.notif_repo.mark_read(notification_id)
        if res:
            event_dispatcher.dispatch(
                event_type="notification_read",
                data={"id": notification_id},
            )
        return res

    def mark_all_as_read(self) -> int:
        count = self.notif_repo.mark_all_read()
        event_dispatcher.dispatch(
            event_type="notifications_all_read",
            data={"count": count},
        )
        return count

    def get_unread_count(self) -> int:
        return self.notif_repo.get_unread_count()


# Global singleton instance
notification_manager = NotificationManager()

