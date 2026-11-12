"""
Tests for read-only Git integration module (core/git_manager.py).
"""

from pathlib import Path
import git
import pytest

from core.git_manager import GitManager


def test_git_manager_init_valid(temp_git_repo: Path):
    gm = GitManager(temp_git_repo)
    assert gm.repo_path == temp_git_repo.resolve()


def test_git_manager_init_invalid_path(tmp_path: Path):
    non_existent = tmp_path / "does_not_exist"
    with pytest.raises(FileNotFoundError):
        GitManager(non_existent)


def test_git_manager_init_non_git_dir(tmp_path: Path):
    plain_dir = tmp_path / "plain_dir"
    plain_dir.mkdir()
    with pytest.raises(ValueError, match="not a valid Git repository"):
        GitManager(plain_dir)


def test_get_current_branch(temp_git_repo: Path):
    gm = GitManager(temp_git_repo)
    branch = gm.get_current_branch()
    assert branch in ["main", "master"]


def test_get_latest_commit(temp_git_repo: Path):
    gm = GitManager(temp_git_repo)
    commit = gm.get_latest_commit()
    assert commit is not None
    assert commit["message"] == "Initial commit"
    assert commit["author_name"] == "Test User"
    assert commit["author_email"] == "testuser@example.com"
    assert len(commit["hexsha"]) == 40
    assert len(commit["short_hash"]) == 7


def test_git_status_clean_repo(temp_git_repo: Path):
    gm = GitManager(temp_git_repo)
    status = gm.get_git_status()

    assert status["is_clean"] is True
    assert status["staged_files"] == []
    assert status["unstaged_files"] == []
    assert status["changes"]["untracked"] == []
    assert status["changes"]["modified"] == []
    assert status["changes"]["deleted"] == []


def test_detect_modified_files(temp_git_repo: Path):
    # Modify an existing tracked file
    readme = temp_git_repo / "README.md"
    readme.write_text("Modified README content\n", encoding="utf-8")

    gm = GitManager(temp_git_repo)
    status = gm.get_git_status()

    assert status["is_clean"] is False
    assert "README.md" in status["unstaged_files"]
    assert "README.md" in status["changes"]["modified"]

    # Verify diff content
    unstaged_diff = gm.get_unstaged_diff()
    assert "-Initial content" in unstaged_diff
    assert "+Modified README content" in unstaged_diff


def test_detect_newly_created_untracked_files(temp_git_repo: Path):
    new_file = temp_git_repo / "new_feature.py"
    new_file.write_text("print('Hello AutoGit')\n", encoding="utf-8")

    gm = GitManager(temp_git_repo)
    status = gm.get_git_status()

    assert status["is_clean"] is False
    assert "new_feature.py" in status["changes"]["untracked"]
    assert "new_feature.py" in status["unstaged_files"]


def test_detect_deleted_files(temp_git_repo: Path):
    readme = temp_git_repo / "README.md"
    readme.unlink()

    gm = GitManager(temp_git_repo)
    status = gm.get_git_status()

    assert status["is_clean"] is False
    assert "README.md" in status["changes"]["deleted"]
    assert "README.md" in status["unstaged_files"]


def test_detect_staged_changes(temp_git_repo: Path):
    staged_file = temp_git_repo / "staged.txt"
    staged_file.write_text("Staged content", encoding="utf-8")

    repo = git.Repo(str(temp_git_repo))
    repo.index.add(["staged.txt"])

    gm = GitManager(temp_git_repo)
    status = gm.get_git_status()

    assert "staged.txt" in status["staged_files"]
    assert "staged.txt" in status["changes"]["staged_added"]

    staged_diff = gm.get_staged_diff()
    assert "staged.txt" in staged_diff
    assert "+Staged content" in staged_diff


def test_git_operations_are_strictly_read_only(temp_git_repo: Path):
    """
    Ensure status/diff calls never commit, stage, or alter git tree state.
    """
    repo = git.Repo(str(temp_git_repo))
    initial_commit_count = len(list(repo.iter_commits()))

    # Modify file
    (temp_git_repo / "scratch.txt").write_text("Temporary", encoding="utf-8")

    gm = GitManager(temp_git_repo)
    _ = gm.get_git_status()
    _ = gm.get_diff()
    _ = gm.get_current_branch()
    _ = gm.get_latest_commit()

    # Verify no new commit was created
    final_commit_count = len(list(repo.iter_commits()))
    assert initial_commit_count == final_commit_count
    # Verify file remains untracked
    assert "scratch.txt" in repo.untracked_files

