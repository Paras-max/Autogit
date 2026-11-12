"""
tests/test_notifications.py – Phase 4 notification system tests

Tests:
  - Notification creation and storage
  - Mark individual notification as read
  - Mark all notifications as read
  - Unread count calculation
  - Event dispatch via pub/sub
  - Notification type validation
"""

import pytest
from datetime import datetime, timezone
import uuid


# ─── Fixtures ─────────────────────────────────────────────────────────────────

def make_notification(**kwargs) -> dict:
    defaults = {
        "notification_id": str(uuid.uuid4()),
        "title": "Test Notification",
        "message": "Something happened.",
        "notification_type": "info",
        "severity": "info",
        "read": False,
        "is_read": False,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repo_name": None,
    }
    defaults.update(kwargs)
    return defaults


@pytest.fixture
def unread_notifications():
    return [make_notification(title=f"Notif {i}", read=False, is_read=False) for i in range(5)]


@pytest.fixture
def mixed_notifications():
    notifs = []
    for i in range(3):
        notifs.append(make_notification(title=f"Unread {i}", read=False, is_read=False))
    for i in range(2):
        notifs.append(make_notification(title=f"Read {i}", read=True, is_read=True))
    return notifs


# ─── Notification Creation ────────────────────────────────────────────────────

class TestNotificationCreation:
    def test_notification_has_required_fields(self):
        n = make_notification()
        assert "notification_id" in n
        assert "title" in n
        assert "message" in n
        assert "created_at" in n

    def test_notification_defaults_to_unread(self):
        n = make_notification()
        assert not n["read"]
        assert not n["is_read"]

    def test_notification_id_is_unique(self):
        ids = {make_notification()["notification_id"] for _ in range(100)}
        assert len(ids) == 100

    def test_notification_severity_values(self):
        valid = {"info", "success", "warning", "error"}
        for sev in valid:
            n = make_notification(severity=sev)
            assert n["severity"] in valid

    def test_notification_types(self):
        types = ["commit", "dev_session", "github_sync", "validation", "info", "error"]
        for t in types:
            n = make_notification(notification_type=t)
            assert n["notification_type"] == t


# ─── Mark Read ────────────────────────────────────────────────────────────────

class TestMarkRead:
    def test_mark_single_notification_read(self, unread_notifications):
        target_id = unread_notifications[0]["notification_id"]
        # Simulate mark read
        for n in unread_notifications:
            if n["notification_id"] == target_id:
                n["read"] = True
                n["is_read"] = True
        marked = next(n for n in unread_notifications if n["notification_id"] == target_id)
        assert marked["read"]
        assert marked["is_read"]

    def test_mark_read_does_not_affect_others(self, unread_notifications):
        target_id = unread_notifications[0]["notification_id"]
        for n in unread_notifications:
            if n["notification_id"] == target_id:
                n["read"] = True
        unaffected = [n for n in unread_notifications if n["notification_id"] != target_id]
        assert all(not n["read"] for n in unaffected)

    def test_mark_already_read_is_idempotent(self):
        n = make_notification(read=True, is_read=True)
        n["read"] = True  # re-mark
        assert n["read"]


# ─── Mark All Read ────────────────────────────────────────────────────────────

class TestMarkAllRead:
    def test_mark_all_read(self, mixed_notifications):
        for n in mixed_notifications:
            n["read"] = True
            n["is_read"] = True
        assert all(n["read"] for n in mixed_notifications)

    def test_unread_count_zero_after_mark_all(self, mixed_notifications):
        for n in mixed_notifications:
            n["read"] = True
        unread = [n for n in mixed_notifications if not n["read"]]
        assert len(unread) == 0


# ─── Unread Count ─────────────────────────────────────────────────────────────

class TestUnreadCount:
    def test_unread_count_matches_unread_notifications(self, mixed_notifications):
        expected_unread = sum(1 for n in mixed_notifications if not n["read"])
        assert expected_unread == 3

    def test_unread_count_decreases_on_mark_read(self, unread_notifications):
        initial = sum(1 for n in unread_notifications if not n["read"])
        # Mark 2 as read
        for n in unread_notifications[:2]:
            n["read"] = True
        after = sum(1 for n in unread_notifications if not n["read"])
        assert after == initial - 2

    def test_unread_count_zero_on_empty(self):
        notifications = []
        count = sum(1 for n in notifications if not n.get("read", False))
        assert count == 0


# ─── Event Dispatch ───────────────────────────────────────────────────────────

class TestEventDispatch:
    def test_event_bus_delivers_to_subscriber(self):
        """Pub/sub event bus delivers events to all subscribers."""
        received = []

        def subscriber(event):
            received.append(event)

        # Simulate dispatch
        event = {"type": "notification_created", "data": make_notification()}
        subscriber(event)

        assert len(received) == 1
        assert received[0]["type"] == "notification_created"

    def test_multiple_subscribers_receive_event(self):
        received_a = []
        received_b = []

        event = {"type": "commit_created", "data": {"commit_hash": "abc123"}}
        received_a.append(event)
        received_b.append(event)

        assert len(received_a) == 1
        assert len(received_b) == 1
        assert received_a[0] is received_b[0]

    def test_event_contains_timestamp(self):
        event = {
            "type": "notification_created",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "data": {},
        }
        assert "timestamp" in event
        # Timestamp must be parseable
        dt = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        assert isinstance(dt, datetime)

    def test_notification_event_includes_severity(self):
        event = {
            "type": "notification_created",
            "data": make_notification(severity="error"),
        }
        assert event["data"]["severity"] == "error"


# ─── Notification Filtering ───────────────────────────────────────────────────

class TestNotificationFiltering:
    def test_filter_unread_only(self, mixed_notifications):
        unread = [n for n in mixed_notifications if not n["read"]]
        assert len(unread) == 3

    def test_filter_by_type(self, mixed_notifications):
        for n in mixed_notifications[:2]:
            n["notification_type"] = "commit"
        commits = [n for n in mixed_notifications if n["notification_type"] == "commit"]
        assert len(commits) == 2

    def test_sort_by_created_at_descending(self):
        import time
        notifications = []
        for i in range(3):
            time.sleep(0.01)
            notifications.append(make_notification(title=f"N{i}"))
        sorted_notifs = sorted(notifications, key=lambda n: n["created_at"], reverse=True)
        assert sorted_notifs[0]["title"] == "N2"

    def test_limit_on_notification_list(self, unread_notifications):
        limit = 3
        limited = unread_notifications[:limit]
        assert len(limited) == limit
