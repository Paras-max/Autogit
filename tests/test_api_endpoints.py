"""
Tests for FastAPI REST endpoints (api/routes.py).
"""

from unittest.mock import AsyncMock, patch
import httpx
from fastapi.testclient import TestClient


def test_repository_endpoints_lifecycle(test_client: TestClient, temp_git_repo):
    # 1. Register repository
    res = test_client.post(
        "/repositories",
        json={"path": str(temp_git_repo), "name": "API Test Repo"},
    )
    assert res.status_code == 201
    data = res.json()
    repo_id = data["id"]
    assert data["repository_name"] == "API Test Repo"
    assert data["latest_commit"] is not None

    # 2. List repositories
    res = test_client.get("/repositories")
    assert res.status_code == 200
    repos = res.json()
    assert len(repos) == 1
    assert repos[0]["id"] == repo_id

    # 3. Get specific repository
    res = test_client.get(f"/repositories/{repo_id}")
    assert res.status_code == 200
    assert res.json()["id"] == repo_id

    # 4. Git status endpoint
    res = test_client.get(f"/repositories/{repo_id}/status")
    assert res.status_code == 200
    status_data = res.json()
    assert status_data["is_clean"] is True
    assert status_data["current_branch"] in ["main", "master"]

    # 5. Git branches endpoint
    res = test_client.get(f"/repositories/{repo_id}/branches")
    assert res.status_code == 200
    branches_data = res.json()
    assert branches_data["current_branch"] in ["main", "master"]
    assert len(branches_data["branches"]) >= 1

    # 6. Git diff endpoint
    res = test_client.get(f"/repositories/{repo_id}/diff")
    assert res.status_code == 200
    diff_data = res.json()
    assert "staged" in diff_data
    assert "unstaged" in diff_data

    # 7. Git latest commit endpoint
    res = test_client.get(f"/repositories/{repo_id}/commits/latest")
    assert res.status_code == 200
    commit_data = res.json()
    assert commit_data["short_hash"] is not None

    # 8. Delete repository
    res = test_client.delete(f"/repositories/{repo_id}")
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 9. Verify 404 after deletion
    res = test_client.get(f"/repositories/{repo_id}")
    assert res.status_code == 404


def test_monitoring_endpoints(test_client: TestClient, temp_git_repo):
    # Register repo first
    create_res = test_client.post(
        "/repositories", json={"path": str(temp_git_repo)}
    )
    repo_id = create_res.json()["id"]

    # 1. Start monitoring
    res = test_client.post(f"/monitoring/start/{repo_id}")
    assert res.status_code == 200
    assert res.json()["success"] is True

    # 2. Get status
    res = test_client.get(f"/monitoring/status/{repo_id}")
    assert res.status_code == 200
    assert res.json()["is_active"] is True

    # 3. Events list
    res = test_client.get(f"/monitoring/events/{repo_id}")
    assert res.status_code == 200
    assert isinstance(res.json(), list)

    # 4. Stop monitoring
    res = test_client.post(f"/monitoring/stop/{repo_id}")
    assert res.status_code == 200
    assert res.json()["success"] is True


def test_auth_endpoints_and_secret_safety(test_client: TestClient):
    # 1. Mock GitHub validation
    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "login": "monalisa",
        "id": 12345,
        "name": "Mona Lisa",
        "html_url": "https://github.com/monalisa",
    }

    dummy_secret = "ghp_supersecret1234567890abcdef"

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        res = test_client.post(
            "/auth/github/validate",
            json={"token": dummy_secret},
        )
    assert res.status_code == 200
    body = res.json()
    assert body["success"] is True
    assert body["username"] == "monalisa"
    # Ensure raw secret is not in response
    assert dummy_secret not in str(body)

    # 2. Auth status
    res = test_client.get("/auth/status")
    assert res.status_code == 200
    status_body = res.json()
    assert dummy_secret not in str(status_body)
    assert status_body["github"]["username"] == "monalisa"

    # 3. Configure Git identity
    res = test_client.post(
        "/auth/git-identity",
        json={"name": "Alice Developer", "email": "alice@example.com"},
    )
    assert res.status_code == 200
    assert res.json()["name"] == "Alice Developer"

    # 4. Select AI provider
    res = test_client.post(
        "/auth/ai-provider",
        json={"provider": "anthropic"},
    )
    assert res.status_code == 200
    assert "anthropic" in res.json()["message"]

