"""
Git Worktree and isolated working directory manager for AutoGit AI (Phase 3).
Provides isolated work environments so autonomous development never mutates
or interferes with user working directories, dirty files, or active index.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import shutil
import subprocess
from typing import Generator, Optional, Tuple

from config.settings import settings
from utils.logger import logger


class WorktreeError(Exception):
    """Raised when git worktree operations fail."""
    pass


class WorktreeManager:
    """
    Manages isolated Git worktrees for safe autonomous development.
    Creates temporary worktree directories linked to dedicated autonomous branches.
    """

    def __init__(self, base_worktree_dir: Optional[Path] = None):
        self.base_worktree_dir = base_worktree_dir or settings.WORKTREE_BASE_DIR
        self.base_worktree_dir.mkdir(parents=True, exist_ok=True)

    def generate_branch_name(self, prefix: Optional[str] = None) -> str:
        """Generate a timestamped branch name for autonomous development."""
        pfx = prefix or settings.AUTONOMOUS_BRANCH_PREFIX
        ts = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        return f"{pfx}-{ts}"

    def create_worktree(
        self,
        repo_path: Path,
        branch_name: Optional[str] = None,
        base_commit: str = "HEAD",
    ) -> Tuple[Path, str]:
        """
        Create a new git worktree with a dedicated branch.
        Returns: (worktree_path, branch_name)
        """
        repo_path = Path(repo_path).resolve()
        branch = branch_name or self.generate_branch_name()
        safe_branch_name = branch.replace("/", "_").replace("\\", "_")
        worktree_path = self.base_worktree_dir / f"{repo_path.name}_{safe_branch_name}"

        # Clean existing directory if stale
        if worktree_path.exists():
            try:
                shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Failed to clear existing path {worktree_path}: {e}")

        cmd = [
            "git",
            "-C",
            str(repo_path),
            "worktree",
            "add",
            "-b",
            branch,
            str(worktree_path),
            base_commit,
        ]

        logger.info(f"Creating isolated worktree at '{worktree_path}' on branch '{branch}'")
        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
            logger.debug(f"Git worktree add output: {res.stdout.strip()}")
            return worktree_path, branch
        except subprocess.CalledProcessError as e:
            err_msg = e.stderr.strip() or e.stdout.strip()
            logger.error(f"Failed to create git worktree: {err_msg}")
            raise WorktreeError(f"Failed to create git worktree: {err_msg}") from e

    def remove_worktree(self, repo_path: Path, worktree_path: Path, force: bool = True) -> bool:
        """
        Remove an isolated git worktree and cleanup directory.
        """
        repo_path = Path(repo_path).resolve()
        worktree_path = Path(worktree_path).resolve()

        logger.info(f"Removing git worktree at '{worktree_path}'")
        cmd = ["git", "-C", str(repo_path), "worktree", "remove"]
        if force:
            cmd.append("--force")
        cmd.append(str(worktree_path))

        try:
            subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                check=True,
            )
        except subprocess.CalledProcessError as e:
            logger.warning(f"git worktree remove warning: {e.stderr.strip()}")
            # Prune worktrees in case it was partially removed
            subprocess.run(
                ["git", "-C", str(repo_path), "worktree", "prune"],
                capture_output=True,
                text=True,
            )

        # Ensure directory is cleaned
        if worktree_path.exists():
            try:
                shutil.rmtree(worktree_path, ignore_errors=True)
            except Exception as e:
                logger.warning(f"Could not remove worktree folder {worktree_path}: {e}")

        return True

    def prune_stale_worktrees(self, repo_path: Path) -> None:
        """Prune invalid or deleted worktree references."""
        subprocess.run(
            ["git", "-C", str(repo_path), "worktree", "prune"],
            capture_output=True,
            text=True,
        )

    @contextmanager
    def isolated_session(
        self,
        repo_path: Path,
        branch_name: Optional[str] = None,
        base_commit: str = "HEAD",
        cleanup: bool = True,
    ) -> Generator[Tuple[Path, str], None, None]:
        """
        Context manager for running autonomous operations in an isolated worktree.
        Yields (worktree_path, branch_name). Automatically removes worktree on exit if cleanup=True.
        """
        worktree_path, branch = self.create_worktree(repo_path, branch_name, base_commit)
        try:
            yield worktree_path, branch
        finally:
            if cleanup:
                try:
                    self.remove_worktree(repo_path, worktree_path)
                except Exception as e:
                    logger.warning(f"Error during worktree cleanup: {e}")

