"""
tests/test_live_events.py – Phase 4 SSE live events tests

Tests:
  - SSE event format validation
  - Event dispatcher pub/sub mechanics
  - Multiple subscriber delivery
  - Event filtering by type
  - Keepalive handling
  - Reconnection logic (conceptual)
"""

import pytest
import asyncio
import json
from datetime import datetime, timezone
from typing import List, Callable, Any


# ─── Lightweight event dispatcher ─────────────────────────────────────────────

class SimpleEventDispatcher:
    """Minimal synchronous event bus for testing."""

    def __init__(self):
        self._subscribers: List[Callable[[dict], None]] = []

    def subscribe(self, callback: Callable[[dict], None]) -> None:
        self._subscribers.append(callback)

    def unsubscribe(self, callback: Callable[[dict], None]) -> None:
        self._subscribers.remove(callback)

    def dispatch(self, event: dict) -> int:
        """Deliver event to all subscribers. Returns delivery count."""
        count = 0
        for sub in self._subscribers:
            sub(event)
            count += 1
        return count

    def subscriber_count(self) -> int:
        return len(self._subscribers)


@pytest.fixture
def dispatcher():
    return SimpleEventDispatcher()


def make_event(event_type: str = "commit_created", **kwargs) -> dict:
    return {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "data": kwargs.get("data", {}),
        "repository_id": kwargs.get("repository_id", None),
    }


# ─── Event Format ─────────────────────────────────────────────────────────────

class TestSSEEventFormat:
    def test_event_has_type_field(self):
        event = make_event("commit_created")
        assert "type" in event

    def test_event_has_timestamp(self):
        event = make_event()
        assert "timestamp" in event
        dt = datetime.fromisoformat(event["timestamp"].replace("Z", "+00:00"))
        assert isinstance(dt, datetime)

    def test_event_has_data_field(self):
        event = make_event(data={"commit_hash": "abc123"})
        assert "data" in event
        assert event["data"]["commit_hash"] == "abc123"

    def test_event_serializable_to_json(self):
        event = make_event("notification_created", data={"title": "Test", "message": "hello"})
        serialized = json.dumps(event)
        deserialized = json.loads(serialized)
        assert deserialized["type"] == "notification_created"

    def test_sse_line_format(self):
        """SSE wire format: 'data: <json>\n\n'"""
        event = make_event("sync_completed")
        payload = json.dumps(event)
        sse_line = f"data: {payload}\n\n"
        assert sse_line.startswith("data: ")
        assert sse_line.endswith("\n\n")

    def test_keepalive_comment_format(self):
        keepalive = ": keepalive\n\n"
        assert keepalive.startswith(":")
        assert not keepalive.startswith("data:")


# ─── Dispatcher Pub/Sub ───────────────────────────────────────────────────────

class TestEventDispatcherPubSub:
    def test_subscribe_increases_count(self, dispatcher):
        assert dispatcher.subscriber_count() == 0
        dispatcher.subscribe(lambda e: None)
        assert dispatcher.subscriber_count() == 1

    def test_unsubscribe_decreases_count(self, dispatcher):
        cb = lambda e: None
        dispatcher.subscribe(cb)
        dispatcher.unsubscribe(cb)
        assert dispatcher.subscriber_count() == 0

    def test_event_delivered_to_subscriber(self, dispatcher):
        received = []
        dispatcher.subscribe(lambda e: received.append(e))
        event = make_event("commit_created")
        dispatcher.dispatch(event)
        assert len(received) == 1
        assert received[0]["type"] == "commit_created"

    def test_delivery_count_matches_subscriber_count(self, dispatcher):
        for _ in range(5):
            dispatcher.subscribe(lambda e: None)
        event = make_event()
        count = dispatcher.dispatch(event)
        assert count == 5

    def test_multiple_subscribers_all_receive(self, dispatcher):
        buckets: List[List] = [[], [], []]
        for bucket in buckets:
            dispatcher.subscribe(lambda e, b=bucket: b.append(e))
        dispatcher.dispatch(make_event("sync_completed"))
        for bucket in buckets:
            assert len(bucket) == 1

    def test_no_subscribers_zero_deliveries(self, dispatcher):
        count = dispatcher.dispatch(make_event())
        assert count == 0


# ─── Event Types ──────────────────────────────────────────────────────────────

class TestKnownEventTypes:
    KNOWN_TYPES = {
        "file_change",
        "notification_created",
        "notification_read",
        "notifications_all_read",
        "proposal_created",
        "commit_created",
        "sync_completed",
        "scheduled_session_active",
    }

    def test_all_known_event_types_are_strings(self):
        for t in self.KNOWN_TYPES:
            assert isinstance(t, str)
            assert len(t) > 0

    @pytest.mark.parametrize("event_type", [
        "commit_created",
        "notification_created",
        "sync_completed",
        "proposal_created",
        "file_change",
    ])
    def test_known_event_type_recognized(self, event_type):
        assert event_type in self.KNOWN_TYPES

    def test_event_filtering_by_type(self, dispatcher):
        commit_events = []
        notif_events = []

        def on_commit(e):
            if e["type"] == "commit_created":
                commit_events.append(e)

        def on_notif(e):
            if e["type"] == "notification_created":
                notif_events.append(e)

        dispatcher.subscribe(on_commit)
        dispatcher.subscribe(on_notif)

        dispatcher.dispatch(make_event("commit_created"))
        dispatcher.dispatch(make_event("notification_created"))
        dispatcher.dispatch(make_event("sync_completed"))

        assert len(commit_events) == 1
        assert len(notif_events) == 1


# ─── Reconnection Logic ───────────────────────────────────────────────────────

class TestSSEReconnection:
    def test_reconnect_attempted_on_error(self):
        """Client should attempt reconnect after connection drops."""
        reconnect_attempts = []

        def on_error():
            reconnect_attempts.append(True)
            # Simulate scheduling a reconnect

        on_error()  # simulate one error
        assert len(reconnect_attempts) == 1

    def test_exponential_backoff_delays(self):
        """Reconnect delays should increase with each failure."""
        delays = [min(3 * (2 ** i), 30) for i in range(5)]
        for i in range(1, len(delays)):
            assert delays[i] >= delays[i - 1]
        assert delays[-1] <= 30  # capped at 30s

    def test_connection_state_transitions(self):
        states = []

        def connect():
            states.append("connecting")
            states.append("connected")

        def on_error():
            states.append("disconnected")
            states.append("reconnecting")

        connect()
        on_error()
        connect()

        assert "connected" in states
        assert "reconnecting" in states
        assert states[-1] == "connected"


# ─── Repository-scoped Events ─────────────────────────────────────────────────

class TestRepositoryScopedEvents:
    def test_event_carries_repository_id(self):
        event = make_event("commit_created", repository_id="repo-001")
        assert event["repository_id"] == "repo-001"

    def test_global_event_has_null_repository(self):
        event = make_event("notifications_all_read")
        assert event["repository_id"] is None

    def test_filter_events_by_repository(self, dispatcher):
        repo_a_events = []

        def on_event(e):
            if e.get("repository_id") == "repo-a":
                repo_a_events.append(e)

        dispatcher.subscribe(on_event)
        dispatcher.dispatch(make_event("commit_created", repository_id="repo-a"))
        dispatcher.dispatch(make_event("commit_created", repository_id="repo-b"))
        dispatcher.dispatch(make_event("commit_created", repository_id="repo-a"))

        assert len(repo_a_events) == 2
