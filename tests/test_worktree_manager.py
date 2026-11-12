"""
Phase 3 Tests: Git Worktree and Isolated Working Directory Management
"""

from pathlib import Path
import subprocess
import pytest

from core.worktree_manager import WorktreeManager, WorktreeError


@pytest.fixture
def git_repo(tmp_path: Path):
    repo_dir = tmp_path / "repo"
    repo_dir.mkdir()
    subprocess.run(["git", "init", str(repo_dir)], check=True, capture_output=True)
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=str(repo_dir), check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True
    )
    readme = repo_dir / "README.md"
    readme.write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "README.md"], cwd=str(repo_dir), check=True)
    subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_dir), check=True)
    return repo_dir


class TestWorktreeManager:
    def test_generate_branch_name(self, tmp_path):
        wm = WorktreeManager(base_worktree_dir=tmp_path / "worktrees")
        branch = wm.generate_branch_name()
        assert branch.startswith("autogit/dev-")

    def test_create_and_remove_worktree(self, git_repo, tmp_path):
        wt_dir = tmp_path / "worktrees"
        wm = WorktreeManager(base_worktree_dir=wt_dir)

        worktree_path, branch = wm.create_worktree(git_repo)
        assert worktree_path.exists()
        assert (worktree_path / "README.md").exists()
        assert branch.startswith("autogit/dev-")

        # Cleanup worktree
        success = wm.remove_worktree(git_repo, worktree_path)
        assert success is True
        assert not worktree_path.exists()

    def test_isolated_session_context_manager(self, git_repo, tmp_path):
        wt_dir = tmp_path / "worktrees"
        wm = WorktreeManager(base_worktree_dir=wt_dir)

        captured_path = None
        with wm.isolated_session(git_repo) as (worktree_path, branch):
            captured_path = worktree_path
            assert worktree_path.exists()
            assert (worktree_path / "README.md").exists()
            # Write a file in worktree
            (worktree_path / "worktree_file.txt").write_text("isolated")
            assert (worktree_path / "worktree_file.txt").exists()
            # Must NOT exist in main repo
            assert not (git_repo / "worktree_file.txt").exists()

        # After context exit, worktree should be removed
        assert not captured_path.exists()

    def test_create_worktree_invalid_repo_raises_error(self, tmp_path):
        wm = WorktreeManager(base_worktree_dir=tmp_path / "worktrees")
        non_git = tmp_path / "non_git"
        non_git.mkdir()
        with pytest.raises(WorktreeError):
            wm.create_worktree(non_git)

