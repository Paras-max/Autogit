"""
Tests for Phase 2 FastAPI Automation and Execution Endpoints (api/execution_routes.py).
"""

from pathlib import Path
from fastapi.testclient import TestClient


def test_automation_settings_endpoints(test_client: TestClient, temp_git_repo: Path):
    # Register repo first
    create_res = test_client.post(
        "/repositories", json={"path": str(temp_git_repo)}
    )
    repo_id = create_res.json()["id"]

    # 1. Get default settings (Smart mode, auto_commit=False)
    get_res = test_client.get(f"/automation/settings/{repo_id}")
    assert get_res.status_code == 200
    data = get_res.json()
    assert data["repository_id"] == repo_id
    assert data["execution_mode"] == "smart"
    assert data["auto_commit_enabled"] is False

    # 2. Update settings
    post_res = test_client.post(
        f"/automation/settings/{repo_id}",
        json={
            "quiet_period_seconds": 5.0,
            "protected_branches": ["main", "master", "release"],
        },
    )
    assert post_res.status_code == 200
    updated = post_res.json()
    assert updated["quiet_period_seconds"] == 5.0
    assert "release" in updated["protected_branches"]


def test_mode_endpoints(test_client: TestClient, temp_git_repo: Path):
    create_res = test_client.post(
        "/repositories", json={"path": str(temp_git_repo)}
    )
    repo_id = create_res.json()["id"]

    # Get mode
    res = test_client.get(f"/automation/mode/{repo_id}")
    assert res.status_code == 200
    assert res.json()["execution_mode"] == "smart"

    # Set mode to auto with explicit confirmation
    res_set = test_client.post(
        f"/automation/mode/{repo_id}",
        json={"mode": "auto", "enable_auto_commit": True},
    )
    assert res_set.status_code == 200
    assert res_set.json()["execution_mode"] == "auto"
    assert res_set.json()["auto_commit_enabled"] is True


def test_proposal_lifecycle_api(test_client: TestClient, temp_git_repo: Path):
    create_res = test_client.post(
        "/repositories", json={"path": str(temp_git_repo)}
    )
    repo_id = create_res.json()["id"]

    # Make file change
    (temp_git_repo / "api_feature.py").write_text("print('feature')\n", encoding="utf-8")

    # 1. Analyze
    analyze_res = test_client.post(
        f"/automation/analyze/{repo_id}",
        json={"user_hint": "Implemented feature API"},
    )
    assert analyze_res.status_code == 200
    analysis = analyze_res.json()
    assert analysis["success"] is True
    exec_id = analysis["execution_id"]
    assert analysis["status"] == "awaiting_approval"

    # 2. Get Analysis Details
    detail_res = test_client.get(f"/automation/analysis/{exec_id}")
    assert detail_res.status_code == 200
    detail = detail_res.json()
    assert detail["execution_id"] == exec_id
    assert "api_feature.py" in detail["proposal"]["proposed_files"]

    # 3. Edit Message
    edit_res = test_client.post(
        f"/automation/proposals/{exec_id}/edit-message",
        json={"new_message": "feat(api): custom user edited message"},
    )
    assert edit_res.status_code == 200
    assert edit_res.json()["new_message"] == "feat(api): custom user edited message"

    # 4. Approve Proposal
    appr_res = test_client.post(
        f"/automation/proposals/{exec_id}/approve",
        json={"approved_by": "api_test", "notes": "Approved for merge"},
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["status"] == "approved"

    # 5. Execute Proposal
    exec_res = test_client.post(f"/automation/execute/{exec_id}")
    assert exec_res.status_code == 200
    exec_data = exec_res.json()
    assert exec_data["success"] is True
    assert exec_data["commit_hash"] is not None

    # 6. List Executions
    hist_res = test_client.get(f"/automation/executions/{repo_id}")
    assert hist_res.status_code == 200
    executions = hist_res.json()
    assert len(executions) >= 1
    assert executions[0]["status"] == "committed"


def test_validate_endpoint(test_client: TestClient, temp_git_repo: Path):
    create_res = test_client.post(
        "/repositories", json={"path": str(temp_git_repo)}
    )
    repo_id = create_res.json()["id"]

    val_res = test_client.post(f"/automation/validate/{repo_id}")
    assert val_res.status_code == 200
    data = val_res.json()
    assert "overall_status" in data
    assert "secret_scan" in data
    assert "policies" in data

