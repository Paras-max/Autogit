"""
Phase 3 Tests: FastAPI Scheduler and Permission Endpoints
"""

import dataclasses
import pytest
from fastapi.testclient import TestClient

from api.routes import get_db
from database.db import DatabaseManager


@pytest.fixture
def mem_db():
    return DatabaseManager(":memory:")


@pytest.fixture
def test_client(mem_db):
    from main import app
    app.dependency_overrides[get_db] = lambda: mem_db
    client = TestClient(app)
    yield client
    app.dependency_overrides.clear()


@pytest.fixture
def repo_id(mem_db):
    repo = mem_db.add_repository(
        name="ApiTestRepo",
        path="/some/fake/path",
        current_branch="main",
    )
    return repo.id


class TestPermissionsAPI:
    def test_get_default_permissions(self, test_client, repo_id):
        resp = test_client.get(f"/repositories/{repo_id}/permissions")
        assert resp.status_code == 200
        data = resp.json()
        assert data["repository_id"] == repo_id
        assert data["autonomous_development_enabled"] is False
        assert data["auto_commit_enabled"] is False
        assert data["remote_push_enabled"] is False

    def test_enable_autonomous_development_via_api(self, test_client, repo_id):
        resp = test_client.post(f"/repositories/{repo_id}/permissions/enable-development")
        assert resp.status_code == 200
        data = resp.json()
        assert data["autonomous_development_enabled"] is True

    def test_disable_autonomous_development_via_api(self, test_client, repo_id):
        # First enable
        test_client.post(f"/repositories/{repo_id}/permissions/enable-development")
        # Then disable
        resp = test_client.post(f"/repositories/{repo_id}/permissions/disable-development")
        assert resp.status_code == 200
        assert resp.json()["autonomous_development_enabled"] is False

    def test_update_permissions_selectively(self, test_client, repo_id):
        resp = test_client.put(
            f"/repositories/{repo_id}/permissions",
            json={"autonomous_development_enabled": True, "auto_commit_enabled": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["autonomous_development_enabled"] is True
        assert data["auto_commit_enabled"] is False

    def test_revoke_all_permissions(self, test_client, repo_id):
        # First enable development
        test_client.post(f"/repositories/{repo_id}/permissions/enable-development")
        # Revoke all
        resp = test_client.post(f"/repositories/{repo_id}/permissions/revoke")
        assert resp.status_code == 200
        data = resp.json()
        assert data["monitoring_enabled"] is False
        assert data["autonomous_development_enabled"] is False

    def test_permissions_endpoint_404_for_missing_repo(self, test_client):
        resp = test_client.get("/repositories/99999/permissions")
        assert resp.status_code == 404


class TestSchedulerAPI:
    def test_get_current_weekly_schedule(self, test_client):
        resp = test_client.get("/scheduler/weekly")
        assert resp.status_code == 200
        data = resp.json()
        assert "week_identifier" in data
        assert len(data["sessions"]) == 5
        assert data["timezone"] is not None

    def test_sessions_are_exactly_5(self, test_client):
        resp = test_client.get("/scheduler/weekly")
        sessions = resp.json()["sessions"]
        assert len(sessions) == 5

    def test_schedule_dates_are_unique(self, test_client):
        resp = test_client.get("/scheduler/weekly")
        sessions = resp.json()["sessions"]
        dates = [s["scheduled_date"] for s in sessions]
        assert len(set(dates)) == 5

    def test_pause_scheduler(self, test_client):
        resp = test_client.post("/scheduler/pause")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_resume_scheduler(self, test_client):
        resp = test_client.post("/scheduler/resume")
        assert resp.status_code == 200
        assert resp.json()["success"] is True

    def test_scheduler_status_endpoint(self, test_client):
        resp = test_client.get("/scheduler/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "is_active" in data
        assert "current_time" in data
        assert "is_scheduled_today" in data


class TestDevelopmentTasksAPI:
    def test_add_task_via_api(self, test_client, repo_id):
        resp = test_client.post(
            f"/development/{repo_id}/tasks",
            json={
                "title": "Add unit tests",
                "description": "Cover utility functions",
                "task_type": "test",
                "priority": "high",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "Add unit tests"
        assert data["status"] == "pending"
        assert data["priority"] == "high"

    def test_list_tasks_for_repo(self, test_client, repo_id):
        # Add a task first
        test_client.post(
            f"/development/{repo_id}/tasks",
            json={"title": "Refactor helpers", "task_type": "refactor", "priority": "medium"},
        )
        resp = test_client.get(f"/development/{repo_id}/tasks")
        assert resp.status_code == 200
        tasks = resp.json()
        assert len(tasks) >= 1

    def test_add_task_404_for_missing_repo(self, test_client):
        resp = test_client.post(
            "/development/99999/tasks",
            json={"title": "Any task", "task_type": "feature", "priority": "low"},
        )
        assert resp.status_code == 404

    def test_run_development_blocked_without_permission(self, test_client, repo_id):
        """Running development without autonomous_development enabled must return 403."""
        resp = test_client.post(f"/development/{repo_id}/run", json={})
        assert resp.status_code == 403

