"""
Read-only Git manager integrating Git CLI and GitPython.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import git
from git.exc import GitCommandError, InvalidGitRepositoryError, NoSuchPathError

from utils.logger import logger


class GitManager:
    """
    Dedicated Git integration module for AutoGit AI.
    NOTE: In Phase 1, all Git operations are strictly READ-ONLY.
    No staging, committing, pushing, pulling, or resetting is performed.
    """

    def __init__(self, repo_path: Path | str):
        self.repo_path = Path(repo_path).resolve()
        if not self.repo_path.exists():
            raise FileNotFoundError(f"Repository path does not exist: {self.repo_path}")
        try:
            self.repo = git.Repo(str(self.repo_path))
        except (InvalidGitRepositoryError, NoSuchPathError) as e:
            raise ValueError(f"Path is not a valid Git repository: {self.repo_path}") from e

    def get_current_branch(self) -> str:
        """Retrieve current branch name or 'HEAD detached' / 'unborn'."""
        try:
            if self.repo.head.is_detached:
                return f"detached at {self.repo.head.commit.hexsha[:7]}"
            return self.repo.active_branch.name
        except TypeError:
            # Typically happens on a fresh repo with no commits (orphan/unborn branch)
            try:
                branch = self.repo.git.symbolic_ref("--short", "HEAD")
                return branch.strip()
            except Exception:
                return "main"
        except Exception as e:
            logger.warning(f"Could not determine current branch for {self.repo_path}: {e}")
            return "unknown"

    def get_remote_url(self, remote_name: str = "origin") -> Optional[str]:
        """Retrieve the URL for a remote, defaults to 'origin'."""
        try:
            if remote_name in [r.name for r in self.repo.remotes]:
                return self.repo.remotes[remote_name].url
            if self.repo.remotes:
                return self.repo.remotes[0].url
            return None
        except Exception as e:
            logger.warning(f"Could not retrieve remote URL: {e}")
            return None

    def get_remotes(self) -> List[Dict[str, str]]:
        """List configured remotes."""
        try:
            return [{"name": r.name, "url": r.url} for r in self.repo.remotes]
        except Exception as e:
            logger.warning(f"Could not retrieve remotes: {e}")
            return []

    def get_branches(self) -> List[str]:
        """List local branches."""
        try:
            return [b.name for b in self.repo.branches]
        except Exception as e:
            logger.warning(f"Could not list branches: {e}")
            return []

    def get_latest_commit(self) -> Optional[Dict[str, Any]]:
        """Retrieve the latest commit info, or None if repo has no commits."""
        try:
            commit = self.repo.head.commit
            return {
                "hexsha": commit.hexsha,
                "short_hash": commit.hexsha[:7],
                "message": commit.message.strip(),
                "author_name": commit.author.name,
                "author_email": commit.author.email,
                "authored_datetime": commit.authored_datetime.isoformat(),
                "committed_datetime": commit.committed_datetime.isoformat(),
            }
        except (ValueError, TypeError, GitCommandError):
            # No commits in repository yet
            return None

    def get_file_changes(self) -> Dict[str, List[str]]:
        """
        Identify categorized file changes in the working directory using Git porcelain status:
        - untracked (newly created)
        - modified (unstaged)
        - deleted (unstaged)
        - staged_added
        - staged_modified
        - staged_deleted
        - renamed
        """
        changes: Dict[str, List[str]] = {
            "untracked": [],
            "modified": [],
            "deleted": [],
            "staged_added": [],
            "staged_modified": [],
            "staged_deleted": [],
            "renamed": [],
        }

        try:
            raw_status = self.repo.git.status("--porcelain=v1", "-uall")
        except Exception as e:
            logger.warning(f"Error executing git status: {e}")
            return changes

        if not raw_status.strip():
            return changes

        for line in raw_status.splitlines():
            if len(line) < 4:
                continue
            x = line[0]
            y = line[1]
            file_path = line[3:].strip()

            # Handle untracked
            if x == "?" and y == "?":
                changes["untracked"].append(file_path)
                continue

            # Handle index (staged) status
            if x == "A":
                changes["staged_added"].append(file_path)
            elif x == "M":
                changes["staged_modified"].append(file_path)
            elif x == "D":
                changes["staged_deleted"].append(file_path)
            elif x == "R":
                changes["renamed"].append(file_path)

            # Handle worktree (unstaged) status
            if y == "M":
                changes["modified"].append(file_path)
            elif y == "D":
                changes["deleted"].append(file_path)

        return changes

    def get_git_status(self) -> Dict[str, Any]:
        """
        Retrieve comprehensive Git status including branches, latest commit,
        staged/unstaged files, and remote configuration.
        """
        branch = self.get_current_branch()
        latest_commit = self.get_latest_commit()
        remote_url = self.get_remote_url()
        changes = self.get_file_changes()

        staged_files = (
            changes["staged_added"]
            + changes["staged_modified"]
            + changes["staged_deleted"]
            + changes["renamed"]
        )
        unstaged_files = (
            changes["modified"]
            + changes["deleted"]
            + changes["untracked"]
        )
        is_clean = len(staged_files) == 0 and len(unstaged_files) == 0

        remotes = [
            {"name": r.name, "url": r.url}
            for r in self.repo.remotes
        ]

        return {
            "repository_path": str(self.repo_path),
            "current_branch": branch,
            "is_clean": is_clean,
            "remote_url": remote_url,
            "remotes": remotes,
            "latest_commit": latest_commit,
            "staged_files": staged_files,
            "unstaged_files": unstaged_files,
            "changes": changes,
        }

    def get_unstaged_diff(self, file_path: Optional[str] = None) -> str:
        """
        Retrieve diff of working directory against index (unstaged diff).
        Equivalent to `git diff` [file_path].
        """
        try:
            args = ["diff"]
            if file_path:
                args.extend(["--", file_path])
            return self.repo.git.execute(["git"] + args)
        except Exception as e:
            logger.warning(f"Error getting unstaged diff: {e}")
            return ""

    def get_staged_diff(self, file_path: Optional[str] = None) -> str:
        """
        Retrieve diff of staged changes against HEAD.
        Equivalent to `git diff --cached` [file_path].
        """
        try:
            args = ["diff", "--cached"]
            if file_path:
                args.extend(["--", file_path])
            return self.repo.git.execute(["git"] + args)
        except Exception as e:
            logger.warning(f"Error getting staged diff: {e}")
            return ""

    def get_diff(self) -> Dict[str, str]:
        """Retrieve both staged and unstaged diffs."""
        return {
            "unstaged": self.get_unstaged_diff(),
            "staged": self.get_staged_diff(),
        }
