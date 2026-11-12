"""
Tests for Staging Manager and Git Executor (core/staging_manager.py, core/git_executor.py).
Focuses on preserving pre-existing staged files and unrelated working tree files.
"""

from pathlib import Path
import git
import pytest

from core.git_executor import GitExecutor
from core.git_manager import GitManager
from core.staging_manager import StagingManager
from database.db import DatabaseManager
from database.models import RepositoryAutomationSettingsModel


def test_selective_staging_only_stages_target_files(temp_git_repo: Path):
    file_a = temp_git_repo / "file_a.py"
    file_b = temp_git_repo / "file_b.py"
    file_a.write_text("print('A')\n", encoding="utf-8")
    file_b.write_text("print('B')\n", encoding="utf-8")

    staging_mgr = StagingManager(temp_git_repo)
    success, staged, err = staging_mgr.stage_files_selectively(["file_a.py"])

    assert success is True
    assert staged == ["file_a.py"]

    # Verify via git status: only file_a is staged, file_b is untracked
    git_mgr = GitManager(temp_git_repo)
    status = git_mgr.get_git_status()
    assert "file_a.py" in status["staged_files"]
    assert "file_b.py" in status["changes"]["untracked"]


def test_isolated_commit_preserves_preexisting_staged_changes(temp_git_repo: Path, temp_db: DatabaseManager):
    """
    CRITICAL SAFETY TEST:
    Developer stages 'user_staged.py' manually.
    AutoGit AI creates a commit containing ONLY 'autogit_target.py'.
    Verify:
    1. autogit_target.py is committed.
    2. user_staged.py is STILL staged in the index and was NOT committed.
    """
    repo = git.Repo(temp_git_repo)

    # 1. Developer stages user_staged.py
    user_file = temp_git_repo / "user_staged.py"
    user_file.write_text("# Staged by developer\n", encoding="utf-8")
    repo.index.add(["user_staged.py"])

    # Verify user_staged.py is staged in Git
    assert "user_staged.py" in [entry[0] for entry in repo.index.entries.keys()]

    # 2. AutoGit AI creates autogit_target.py
    target_file = temp_git_repo / "autogit_target.py"
    target_file.write_text("# Created by AutoGit\n", encoding="utf-8")

    executor = GitExecutor(temp_git_repo, database=temp_db)
    settings = RepositoryAutomationSettingsModel(
        repository_id=1,
        execution_mode="smart",
        protected_branches=[],
    )

    result = executor.execute_commit(
        files_to_commit=["autogit_target.py"],
        commit_message="feat: add autogit target file",
        settings=settings,
    )

    assert result["success"] is True
    commit_hash = result["commit_hash"]
    assert commit_hash is not None

    # Check commit contents
    commit_obj = repo.commit(commit_hash)
    committed_names = [item.path for item in commit_obj.tree.traverse()]
    assert "autogit_target.py" in committed_names
    assert "user_staged.py" not in committed_names  # NOT in the commit!

    # Verify that user_staged.py is STILL STAGED in the developer's index!
    current_staged = GitManager(temp_git_repo).get_git_status()["staged_files"]
    assert "user_staged.py" in current_staged


def test_isolated_commit_preserves_unrelated_unstaged_files(temp_git_repo: Path, temp_db: DatabaseManager):
    """
    Verifies that unrelated working tree files are completely untouched by commit execution.
    """
    target = temp_git_repo / "target.py"
    target.write_text("content\n", encoding="utf-8")

    unrelated = temp_git_repo / "unrelated_dev_work.txt"
    unrelated.write_text("WIP notes\n", encoding="utf-8")

    executor = GitExecutor(temp_git_repo, database=temp_db)
    settings = RepositoryAutomationSettingsModel(
        repository_id=1,
        execution_mode="smart",
        protected_branches=[],
    )

    res = executor.execute_commit(
        files_to_commit=["target.py"],
        commit_message="feat: commit target only",
        settings=settings,
    )

    assert res["success"] is True
    assert unrelated.exists()
    assert unrelated.read_text(encoding="utf-8") == "WIP notes\n"

    # Unrelated file remains untracked in working directory
    git_mgr = GitManager(temp_git_repo)
    assert "unrelated_dev_work.txt" in git_mgr.get_git_status()["changes"]["untracked"]


def test_executor_blocks_empty_commit(temp_git_repo: Path, temp_db: DatabaseManager):
    executor = GitExecutor(temp_git_repo, database=temp_db)
    settings = RepositoryAutomationSettingsModel(repository_id=1)

    # Empty file list
    res = executor.execute_commit(
        files_to_commit=[],
        commit_message="feat: empty",
        settings=settings,
    )
    assert res["success"] is False
    assert "empty file list" in res["error"].lower()


def test_executor_verifies_commit_hash(temp_git_repo: Path, temp_db: DatabaseManager):
    executor = GitExecutor(temp_git_repo, database=temp_db)
    # Valid existing commit hash from temp_git_repo fixture
    repo = git.Repo(temp_git_repo)
    head_hash = repo.head.commit.hexsha

    assert executor.verify_commit_exists(head_hash) is True
    assert executor.verify_commit_exists("0000000000000000000000000000000000000000") is False

