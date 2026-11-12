"""
Tests for Execution Controller (core/execution_controller.py).
Tests Smart Commit, Auto Commit, approval/rejection, stale proposal invalidation, and locking.
"""

from pathlib import Path
import git
import pytest

from core.execution_controller import ExecutionController
from core.repository_manager import RepositoryManager
from database.db import DatabaseManager
from database.execution_repository import ExecutionRepository
from database.models import RepositoryAutomationSettingsModel


@pytest.mark.asyncio
async def test_smart_commit_requires_explicit_approval_then_executes(
    temp_git_repo: Path, temp_db: DatabaseManager
):
    repo_mgr = RepositoryManager(database=temp_db)
    repo = repo_mgr.add_repository(str(temp_git_repo))

    # Make a change
    feature_file = temp_git_repo / "feature.py"
    feature_file.write_text("def run_feature(): return True\n", encoding="utf-8")

    controller = ExecutionController(database=temp_db)

    # 1. Analyze and propose
    res = await controller.analyze_and_propose(repository_id=repo.id)
    assert res["success"] is True
    assert res["mode"] == "smart"
    assert res["status"] == "awaiting_approval"
    exec_id = res["execution_id"]

    # Verify no commit was made yet
    git_repo = git.Repo(temp_git_repo)
    initial_commits = len(list(git_repo.iter_commits()))

    # Attempting to execute unapproved proposal should fail
    exec_res_unapproved = controller.execute_proposal(exec_id)
    assert exec_res_unapproved["success"] is False
    assert "cannot be executed" in exec_res_unapproved["error"].lower()

    # 2. Approve proposal
    appr_res = controller.approve_proposal(exec_id, approved_by="test_user")
    assert appr_res["success"] is True
    assert appr_res["status"] == "approved"

    # 3. Execute approved proposal
    exec_res = controller.execute_proposal(exec_id)
    assert exec_res["success"] is True
    assert exec_res["commit_hash"] is not None

    # Verify commit count increased by 1
    new_commits = len(list(git_repo.iter_commits()))
    assert new_commits == initial_commits + 1


@pytest.mark.asyncio
async def test_proposal_rejection_workflow(temp_git_repo: Path, temp_db: DatabaseManager):
    repo_mgr = RepositoryManager(database=temp_db)
    repo = repo_mgr.add_repository(str(temp_git_repo))

    (temp_git_repo / "wip.py").write_text("wip = 1\n", encoding="utf-8")

    controller = ExecutionController(database=temp_db)
    prop = await controller.analyze_and_propose(repository_id=repo.id)
    exec_id = prop["execution_id"]

    # Reject proposal
    rej = controller.reject_proposal(exec_id, reason="Not ready for commit")
    assert rej["success"] is True
    assert rej["status"] == "rejected"

    # Execution fails
    exec_fail = controller.execute_proposal(exec_id)
    assert exec_fail["success"] is False


@pytest.mark.asyncio
async def test_edit_proposal_message(temp_git_repo: Path, temp_db: DatabaseManager):
    repo_mgr = RepositoryManager(database=temp_db)
    repo = repo_mgr.add_repository(str(temp_git_repo))

    (temp_git_repo / "docs.md").write_text("# Documentation\n", encoding="utf-8")

    controller = ExecutionController(database=temp_db)
    prop = await controller.analyze_and_propose(repository_id=repo.id)
    exec_id = prop["execution_id"]

    # Edit message
    new_msg = "docs: update project documentation guide"
    edit_res = controller.edit_proposal_message(exec_id, new_msg)
    assert edit_res["success"] is True
    assert edit_res["new_message"] == new_msg

    # Approve and execute
    controller.approve_proposal(exec_id)
    exec_res = controller.execute_proposal(exec_id)
    assert exec_res["success"] is True

    # Check commit message in git
    git_repo = git.Repo(temp_git_repo)
    assert git_repo.head.commit.message.strip() == new_msg


@pytest.mark.asyncio
async def test_auto_commit_mode_on_unprotected_branch(temp_git_repo: Path, temp_db: DatabaseManager):
    """
    Tests that Auto Commit works when explicitly enabled on an unprotected branch.
    """
    repo_mgr = RepositoryManager(database=temp_db)
    repo = repo_mgr.add_repository(str(temp_git_repo))

    # Switch to feature branch
    git_repo = git.Repo(temp_git_repo)
    git_repo.git.checkout("-b", "feature/auto-test")

    exec_repo = ExecutionRepository(database=temp_db)
    # Explicitly enable auto commit
    exec_repo.save_automation_settings(
        RepositoryAutomationSettingsModel(
            repository_id=repo.id,
            execution_mode="auto",
            auto_commit_enabled=True,
            protected_branches=["main", "master"],
        )
    )

    (temp_git_repo / "auto_feature.py").write_text("print('Auto commit')\n", encoding="utf-8")

    controller = ExecutionController(database=temp_db)
    res = await controller.analyze_and_propose(repository_id=repo.id)

    assert res["success"] is True
    assert res["mode"] == "auto"
    assert res["status"] == "committed"
    assert res["commit_hash"] is not None

    # Verify commit exists in Git
    assert git_repo.head.commit.hexsha == res["commit_hash"]


@pytest.mark.asyncio
async def test_auto_commit_blocked_on_protected_branch(temp_git_repo: Path, temp_db: DatabaseManager):
    """
    Tests that Auto Commit is blocked on protected branch ('master' or 'main')
    and falls back to awaiting_approval.
    """
    repo_mgr = RepositoryManager(database=temp_db)
    repo = repo_mgr.add_repository(str(temp_git_repo))

    exec_repo = ExecutionRepository(database=temp_db)
    exec_repo.save_automation_settings(
        RepositoryAutomationSettingsModel(
            repository_id=repo.id,
            execution_mode="auto",
            auto_commit_enabled=True,
            protected_branches=["main", "master"],
        )
    )

    (temp_git_repo / "change.txt").write_text("On protected branch\n", encoding="utf-8")

    controller = ExecutionController(database=temp_db)
    res = await controller.analyze_and_propose(repository_id=repo.id)

    assert res["success"] is True
    # Must NOT be committed! Must fallback to awaiting_approval due to branch protection
    assert res["status"] == "awaiting_approval"


@pytest.mark.asyncio
async def test_stale_proposal_invalidation(temp_git_repo: Path, temp_db: DatabaseManager):
    """
    If the working tree changes after proposal generation (e.g. file reverted),
    executing the proposal must detect the change and invalidate the proposal safely.
    """
    repo_mgr = RepositoryManager(database=temp_db)
    repo = repo_mgr.add_repository(str(temp_git_repo))

    test_file = temp_git_repo / "stale_test.py"
    test_file.write_text("change\n", encoding="utf-8")

    controller = ExecutionController(database=temp_db)
    prop = await controller.analyze_and_propose(repository_id=repo.id)
    exec_id = prop["execution_id"]

    controller.approve_proposal(exec_id)

    # Developer reverts the change outside before execution
    test_file.unlink()

    # Attempt execution
    res = controller.execute_proposal(exec_id)
    assert res["success"] is False
    assert "stale proposal" in res["error"].lower()

    # Status in database should be 'invalidated'
    exec_repo = ExecutionRepository(temp_db)
    rec = exec_repo.get_execution(exec_id)
    assert rec.status == "invalidated"
