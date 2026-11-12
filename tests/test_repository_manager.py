"""
Tests for Repository Manager (core/repository_manager.py).
"""

from pathlib import Path
import pytest

from core.repository_manager import RepositoryManager
from database.db import DatabaseManager


def test_register_valid_repository(temp_git_repo: Path, temp_db: DatabaseManager):
    mgr = RepositoryManager(database=temp_db)
    repo = mgr.add_repository(str(temp_git_repo), name="My Test Repo")

    assert repo.id is not None
    assert repo.repository_name == "My Test Repo"
    assert repo.repository_path == str(temp_git_repo.resolve())
    assert repo.current_branch in ["main", "master"]


def test_reject_invalid_repository_path(tmp_path: Path, temp_db: DatabaseManager):
    mgr = RepositoryManager(database=temp_db)
    non_existent = tmp_path / "non_existent_folder"

    with pytest.raises(ValueError, match="does not exist"):
        mgr.add_repository(str(non_existent))


def test_reject_non_git_directory(tmp_path: Path, temp_db: DatabaseManager):
    plain_dir = tmp_path / "regular_folder"
    plain_dir.mkdir()

    mgr = RepositoryManager(database=temp_db)
    with pytest.raises(ValueError, match="not a Git repository"):
        mgr.add_repository(str(plain_dir))


def test_list_and_get_repository_info(temp_git_repo: Path, temp_db: DatabaseManager):
    mgr = RepositoryManager(database=temp_db)
    repo = mgr.add_repository(str(temp_git_repo))

    all_repos = mgr.list_repositories()
    assert len(all_repos) == 1
    assert all_repos[0].id == repo.id

    info = mgr.get_repository_info(repo.id)
    assert info is not None
    assert info["id"] == repo.id
    assert info["repository_name"] == temp_git_repo.name
    assert info["latest_commit"] is not None
    assert info["latest_commit"]["message"] == "Initial commit"


def test_remove_repository_leaves_disk_files_untouched(
    temp_git_repo: Path, temp_db: DatabaseManager
):
    mgr = RepositoryManager(database=temp_db)
    repo = mgr.add_repository(str(temp_git_repo))
    repo_id = repo.id
    assert repo_id is not None

    # Check file exists
    readme = temp_git_repo / "README.md"
    assert readme.exists()

    # Remove from AutoGit
    removed = mgr.remove_repository(repo_id)
    assert removed is True

    # Check that repo is no longer in DB
    assert mgr.get_repository_info(repo_id) is None
    assert len(mgr.list_repositories()) == 0

    # Crucial: verify underlying disk files and git repository were NOT deleted or altered
    assert temp_git_repo.exists()
    assert (temp_git_repo / ".git").exists()
    assert readme.exists()


def test_database_persistence_across_restarts(temp_git_repo: Path, tmp_path: Path):
    """
    Verify that repository registration persists when a new DatabaseManager connects.
    """
    db_file = tmp_path / "persistent.db"

    # 1. Register with initial instance
    db1 = DatabaseManager(db_path=db_file)
    mgr1 = RepositoryManager(database=db1)
    repo1 = mgr1.add_repository(str(temp_git_repo), name="Persistent Repo")
    repo_id = repo1.id

    # 2. Simulate complete application restart by spinning up fresh instance on same DB file
    db2 = DatabaseManager(db_path=db_file)
    mgr2 = RepositoryManager(database=db2)
    saved_repos = mgr2.list_repositories()

    assert len(saved_repos) == 1
    assert saved_repos[0].id == repo_id
    assert saved_repos[0].repository_name == "Persistent Repo"
    assert saved_repos[0].repository_path == str(temp_git_repo.resolve())

