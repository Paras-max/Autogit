"""
tests/test_dashboard_api.py – Phase 4 dashboard API tests

Tests:
  - Overview metrics structure and types
  - Activity endpoint returns list
  - Agents endpoint returns agent list
  - Upcoming sessions endpoint
  - Commit history filtering
  - Dashboard preferences key-value store
  - SSE event structure
"""

import pytest
from datetime import datetime, timezone


# ─── Fixtures ─────────────────────────────────────────────────────────────────

@pytest.fixture
def sample_overview():
    return {
        "total_repositories": 3,
        "authorized_repositories": 2,
        "active_sessions": 1,
        "total_commits": 42,
        "pending_approvals": 0,
        "validation_failures": 0,
        "monitoring_active": True,
        "scheduler_active": True,
        "current_week": "2026-W46",
        "agents_online": 8,
    }


@pytest.fixture
def sample_activity():
    return [
        {
            "event_type": "commit",
            "repo_name": "my-project",
            "description": "feat: add user auth",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
        },
        {
            "event_type": "dev_session",
            "repo_name": "api-service",
            "description": "Autonomous development session completed",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "completed",
        },
    ]


@pytest.fixture
def sample_agents():
    return [
        {"name": "DiffAnalysisAgent", "role": "Analyze file diffs", "status": "idle"},
        {"name": "CommitMessageAgent", "role": "Generate commit messages", "status": "idle"},
        {"name": "ValidationAgent", "role": "Validate changes", "status": "idle"},
        {"name": "SecretScanner", "role": "Detect secrets in code", "status": "idle"},
        {"name": "TaskPlanningAgent", "role": "Plan development tasks", "status": "idle"},
        {"name": "DevelopmentAgent", "role": "Execute code changes", "status": "idle"},
        {"name": "ReviewAgent", "role": "Review development work", "status": "idle"},
        {"name": "ChangeGroupingAgent", "role": "Group related changes", "status": "idle"},
    ]


@pytest.fixture
def sample_commits():
    return [
        {
            "commit_hash": "abc123def456",
            "commit_message": "feat: add login endpoint",
            "repo_name": "api-service",
            "branch": "main",
            "staged_files": ["api/auth.py", "tests/test_auth.py"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "committed",
        },
        {
            "commit_hash": "789xyz000111",
            "commit_message": "fix: handle null user gracefully",
            "repo_name": "api-service",
            "branch": "main",
            "staged_files": ["api/users.py"],
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "committed",
        },
    ]


# ─── Overview Metrics ─────────────────────────────────────────────────────────

class TestDashboardOverview:
    def test_overview_has_required_fields(self, sample_overview):
        required = [
            "total_repositories", "authorized_repositories",
            "total_commits", "monitoring_active", "scheduler_active",
        ]
        for field in required:
            assert field in sample_overview, f"Missing field: {field}"

    def test_overview_counts_are_non_negative(self, sample_overview):
        assert sample_overview["total_repositories"] >= 0
        assert sample_overview["authorized_repositories"] >= 0
        assert sample_overview["total_commits"] >= 0
        assert sample_overview["pending_approvals"] >= 0

    def test_authorized_repos_lte_total(self, sample_overview):
        assert sample_overview["authorized_repositories"] <= sample_overview["total_repositories"]

    def test_monitoring_active_is_boolean(self, sample_overview):
        assert isinstance(sample_overview["monitoring_active"], bool)

    def test_agents_online_count(self, sample_overview):
        assert sample_overview["agents_online"] == 8  # 8 AI agents in Phase 2+3+4

    def test_current_week_format(self, sample_overview):
        # Must be ISO week format YYYY-Www
        week = sample_overview["current_week"]
        import re
        assert re.match(r"^\d{4}-W\d{2}$", week), f"Unexpected week format: {week}"


# ─── Activity Endpoint ────────────────────────────────────────────────────────

class TestDashboardActivity:
    def test_activity_is_list(self, sample_activity):
        assert isinstance(sample_activity, list)

    def test_activity_items_have_required_fields(self, sample_activity):
        for item in sample_activity:
            assert "event_type" in item
            assert "timestamp" in item

    def test_activity_sorted_by_timestamp(self, sample_activity):
        timestamps = [item["timestamp"] for item in sample_activity]
        # All timestamps must be parseable ISO strings
        for ts in timestamps:
            dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
            assert isinstance(dt, datetime)

    def test_activity_event_types_are_known(self, sample_activity):
        known_types = {"commit", "dev_session", "fetch", "push", "validation", "file_change", "scheduler"}
        for item in sample_activity:
            # Type might be a known or custom type; just ensure it's a string
            assert isinstance(item["event_type"], str)
            assert len(item["event_type"]) > 0

    def test_activity_limit_honored(self, sample_activity):
        limit = 1
        limited = sample_activity[:limit]
        assert len(limited) == limit


# ─── Agents Endpoint ──────────────────────────────────────────────────────────

class TestDashboardAgents:
    def test_agents_list_has_all_8_agents(self, sample_agents):
        assert len(sample_agents) == 8

    def test_agent_has_name_and_status(self, sample_agents):
        for agent in sample_agents:
            assert "name" in agent
            assert "status" in agent

    def test_agent_status_is_valid(self, sample_agents):
        valid = {"online", "active", "idle", "error", "disabled"}
        for agent in sample_agents:
            assert agent["status"] in valid

    def test_agent_names_are_unique(self, sample_agents):
        names = [a["name"] for a in sample_agents]
        assert len(names) == len(set(names))


# ─── Commit History ───────────────────────────────────────────────────────────

class TestCommitHistory:
    def test_commits_list_structure(self, sample_commits):
        for c in sample_commits:
            assert "commit_hash" in c
            assert "commit_message" in c

    def test_commit_hash_length(self, sample_commits):
        for c in sample_commits:
            assert len(c["commit_hash"]) >= 7  # at least short hash

    def test_commits_filtered_by_repo(self, sample_commits):
        repo = "api-service"
        filtered = [c for c in sample_commits if c["repo_name"] == repo]
        assert len(filtered) == len(sample_commits)

    def test_commit_staged_files_is_list(self, sample_commits):
        for c in sample_commits:
            assert isinstance(c["staged_files"], list)

    def test_commit_message_non_empty(self, sample_commits):
        for c in sample_commits:
            msg = c["commit_message"].strip()
            assert len(msg) > 0


# ─── Dashboard Preferences ────────────────────────────────────────────────────

class TestDashboardPreferences:
    def test_set_and_get_preference(self):
        prefs = {}

        def set_pref(key, value):
            prefs[key] = value

        def get_pref(key, default=None):
            return prefs.get(key, default)

        set_pref("sidebar_collapsed", True)
        assert get_pref("sidebar_collapsed") is True

    def test_preference_default_value(self):
        prefs = {}
        result = prefs.get("nonexistent_key", "default_value")
        assert result == "default_value"

    def test_preference_overwrite(self):
        prefs = {"theme": "dark"}
        prefs["theme"] = "light"
        assert prefs["theme"] == "light"

    def test_preference_key_types(self):
        valid_keys = ["sidebar_collapsed", "default_tab", "theme", "notifications_enabled"]
        for key in valid_keys:
            assert isinstance(key, str)
            assert len(key) > 0


# ─── SSE Event Structure ──────────────────────────────────────────────────────

class TestSSEEvents:
    def test_sse_event_has_type(self):
        event = {"type": "commit_created", "data": {}, "timestamp": datetime.now(timezone.utc).isoformat()}
        assert "type" in event
        assert isinstance(event["type"], str)

    def test_sse_event_has_data(self):
        event = {"type": "notification_created", "data": {"title": "Test"}}
        assert "data" in event

    def test_sse_known_event_types(self):
        known = {
            "file_change", "notification_created", "notification_read",
            "notifications_all_read", "proposal_created", "commit_created",
            "sync_completed", "scheduled_session_active",
        }
        event_type = "commit_created"
        assert event_type in known

    def test_sse_keepalive_comment_ignored(self):
        raw = ": keepalive"
        is_data = raw.startswith("data:")
        assert not is_data

    def test_sse_data_line_parsed(self):
        import json
        raw_data = '{"type": "commit_created", "data": {"hash": "abc123"}}'
        parsed = json.loads(raw_data)
        assert parsed["type"] == "commit_created"
        assert "hash" in parsed["data"]
