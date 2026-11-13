"""
Unit tests for GitHub import functionality and URL rejection in local registration.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch
import pytest
from fastapi.testclient import TestClient

from main import app
from utils.validators import validate_local_path


client = TestClient(app)


def test_validate_local_path_rejects_remote_urls():
    """Verify that validate_local_path immediately rejects remote URLs."""
    urls = [
        "https://github.com/Paras-max/PollingApp",
        "http://github.com/Paras-max/PollingApp.git",
        "git@github.com:Paras-max/PollingApp.git",
        "git://github.com/Paras-max/PollingApp",
        "ssh://git@github.com/Paras-max/PollingApp",
    ]
    for url in urls:
        is_valid, msg, resolved = validate_local_path(url)
        assert is_valid is False
        assert resolved is None
        assert "GitHub URLs cannot be used as local paths" in msg


def test_post_repository_rejects_github_url():
    """POST /repositories should return 400 when given a remote URL."""
    res = client.post(
        "/api/v1/repositories",
        json={"path": "https://github.com/Paras-max/PollingApp"},
    )
    assert res.status_code == 400
    assert "GitHub URLs cannot be used as local paths" in res.json()["detail"]


def test_import_github_rejects_invalid_url():
    """POST /repositories/import-github should reject non-GitHub URLs."""
    res = client.post(
        "/api/v1/repositories/import-github",
        json={
            "github_url": "https://gitlab.com/owner/repo.git",
            "destination_folder": "C:\\fake\\dest",
        },
    )
    assert res.status_code == 400
    assert "Invalid GitHub URL" in res.json()["detail"]


def test_import_github_rejects_relative_destination():
    """POST /repositories/import-github should reject relative destination paths."""
    res = client.post(
        "/api/v1/repositories/import-github",
        json={
            "github_url": "https://github.com/Paras-max/PollingApp.git",
            "destination_folder": "relative/folder",
        },
    )
    assert res.status_code == 400
    assert "must be an absolute path" in res.json()["detail"]


def test_import_github_rejects_existing_non_empty_dir(tmp_path):
    """POST /repositories/import-github should reject existing non-empty non-git destinations."""
    dest_dir = tmp_path / "clones"
    dest_dir.mkdir()
    target_repo_dir = dest_dir / "PollingApp"
    target_repo_dir.mkdir()
    # Put a non-git file
    (target_repo_dir / "dummy.txt").write_text("hello")

    res = client.post(
        "/api/v1/repositories/import-github",
        json={
            "github_url": "https://github.com/Paras-max/PollingApp",
            "destination_folder": str(dest_dir),
        },
    )
    assert res.status_code == 400
    assert "Destination already exists and is not empty" in res.json()["detail"]


@patch("git.Repo.clone_from")
def test_import_github_clones_and_registers_mocked(mock_clone, tmp_path):
    """POST /repositories/import-github clones and registers repository cleanly."""
    dest_dir = tmp_path / "dest"
    dest_dir.mkdir()
    expected_repo_dir = dest_dir / "SampleRepo"

    # Simulate clone creating .git
    def side_effect(url, dest):
        d = Path(dest)
        d.mkdir(parents=True, exist_ok=True)
        (d / ".git").mkdir()
        # Initialize an empty git repo structure so GitManager succeeds
        import git
        git.Repo.init(str(d))

    mock_clone.side_effect = side_effect

    res = client.post(
        "/api/v1/repositories/import-github",
        json={
            "github_url": "https://github.com/Paras-max/SampleRepo.git",
            "destination_folder": str(dest_dir),
            "name": "CustomSample",
        },
    )
    assert res.status_code == 201
    data = res.json()
    assert data["repository_name"] == "CustomSample"
    assert "SampleRepo" in data["repository_path"]
    assert mock_clone.called

