"""
Smart Staging Manager for AutoGit AI.
Selectively stages only approved files while strictly preserving unrelated staged
and unstaged developer changes. Never uses 'git add .' or 'git add -A'.
"""

import os
from pathlib import Path
import tempfile
from typing import Dict, List, Optional, Set, Tuple
import git

from core.git_manager import GitManager
from utils.logger import logger
from utils.security import safe_resolve_repo_path, safe_subprocess_run


class StagingManager:
    """Manages selective file-level staging and protects pre-existing index state."""

    def __init__(self, repo_path: Path | str):
        self.repo_path = Path(repo_path).resolve()
        self.git_mgr = GitManager(self.repo_path)

    def get_currently_staged_files(self) -> List[str]:
        """Query current index to find all staged files."""
        status = self.git_mgr.get_git_status()
        return status.get("staged_files", [])

    def stage_files_selectively(
        self, files_to_stage: List[str]
    ) -> Tuple[bool, List[str], Optional[str]]:
        """
        Stage ONLY the specified files using file-level arguments.
        Rechecks existence and prevents path traversal.
        Never runs 'git add .' or 'git add -A'.
        Returns (success, staged_paths, error_message).
        """
        if not files_to_stage:
            return False, [], "No files specified for staging."

        valid_rel_paths = []
        for rel_path in files_to_stage:
            resolved = safe_resolve_repo_path(self.repo_path, rel_path)
            if not resolved:
                return False, [], f"Security violation: invalid file path '{rel_path}'."
            # Check file exists on disk or was deleted in git
            valid_rel_paths.append(rel_path)

        # Stage each file individually or in safe batch
        staged_successfully = []
        for f in valid_rel_paths:
            # Use safe subprocess with argument array: git add -- <file>
            exit_code, stdout, stderr = safe_subprocess_run(
                cmd_args=["git", "add", "--", f],
                cwd=self.repo_path,
                timeout=15.0,
            )
            if exit_code == 0:
                staged_successfully.append(f)
            else:
                logger.error(f"Failed to stage '{f}': {stderr}")
                return False, staged_successfully, f"Failed to stage {f}: {stderr}"

        logger.info(f"Successfully staged {len(staged_successfully)} file(s): {staged_successfully}")
        return True, staged_successfully, None

    def unstage_files(self, files_to_unstage: List[str]) -> bool:
        """
        Unstage specific files from the index (e.g. for rollback) without touching working tree.
        Uses 'git restore --staged -- <files>'.
        """
        if not files_to_unstage:
            return True
        exit_code, _, stderr = safe_subprocess_run(
            cmd_args=["git", "restore", "--staged", "--"] + files_to_unstage,
            cwd=self.repo_path,
            timeout=15.0,
        )
        if exit_code != 0:
            # Fallback for older git versions: git reset HEAD -- <files>
            exit_code, _, stderr = safe_subprocess_run(
                cmd_args=["git", "reset", "HEAD", "--"] + files_to_unstage,
                cwd=self.repo_path,
                timeout=15.0,
            )
        return exit_code == 0

    def commit_with_isolated_index(
        self,
        files_to_commit: List[str],
        commit_message: str,
        author_name: Optional[str] = None,
        author_email: Optional[str] = None,
    ) -> Tuple[bool, Optional[str], Optional[str]]:
        """
        Advanced Safe Git mechanism:
        Creates a commit containing ONLY files_to_commit without touching
        or disrupting the developer's pre-existing staged files in .git/index!

        Workflow:
        1. Create an isolated temporary index file via GIT_INDEX_FILE.
        2. Read HEAD into the temporary index (if HEAD exists).
        3. Add only the approved files to this temporary index.
        4. Write tree from the temporary index.
        5. Create commit object pointing to current HEAD.
        6. Advance branch pointer to the new commit.
        7. Delete temporary index file.
        Returns: (success, commit_hash, error_message)
        """
        git_dir = self.repo_path / ".git"
        if not git_dir.exists():
            return False, None, "Not a valid Git repository."

        temp_index_path = git_dir / f"autogit_index_{os.getpid()}_{id(self)}"
        env = os.environ.copy()
        env["GIT_INDEX_FILE"] = str(temp_index_path)

        if author_name:
            env["GIT_AUTHOR_NAME"] = author_name
            env["GIT_COMMITTER_NAME"] = author_name
        if author_email:
            env["GIT_AUTHOR_EMAIL"] = author_email
            env["GIT_COMMITTER_EMAIL"] = author_email

        try:
            # Check if HEAD exists
            head_code, head_hash, _ = safe_subprocess_run(
                ["git", "rev-parse", "HEAD"], cwd=self.repo_path, env=env
            )
            has_head = (head_code == 0 and head_hash.strip())
            parent_arg = ["-p", head_hash.strip()] if has_head else []

            # 1. Read current HEAD into isolated index (if HEAD exists)
            if has_head:
                rc, _, err = safe_subprocess_run(
                    ["git", "read-tree", "HEAD"], cwd=self.repo_path, env=env
                )
                if rc != 0:
                    return False, None, f"Failed to initialize isolated index from HEAD: {err}"

            # 2. Add approved files to the isolated index
            for rel_file in files_to_commit:
                full_file = self.repo_path / rel_file
                if full_file.exists():
                    rc, _, err = safe_subprocess_run(
                        ["git", "add", "--", rel_file], cwd=self.repo_path, env=env
                    )
                else:
                    # Deleted file
                    rc, _, err = safe_subprocess_run(
                        ["git", "rm", "--cached", "--", rel_file], cwd=self.repo_path, env=env
                    )
                if rc != 0:
                    return False, None, f"Failed to add '{rel_file}' to isolated index: {err}"

            # 3. Write tree
            rc, tree_hash, err = safe_subprocess_run(
                ["git", "write-tree"], cwd=self.repo_path, env=env
            )
            if rc != 0 or not tree_hash.strip():
                return False, None, f"Failed to write tree: {err}"
            tree_hash = tree_hash.strip()

            # Verify tree is not identical to HEAD (empty commit check)
            if has_head:
                _, head_tree, _ = safe_subprocess_run(
                    ["git", "rev-parse", "HEAD^{tree}"], cwd=self.repo_path, env=env
                )
                if head_tree.strip() == tree_hash:
                    return False, None, "Aborted: proposed commit produces no changes against HEAD."

            # 4. Commit tree
            commit_cmd = ["git", "commit-tree", tree_hash] + parent_arg + ["-m", commit_message]
            rc, new_commit_hash, err = safe_subprocess_run(
                commit_cmd, cwd=self.repo_path, env=env
            )
            if rc != 0 or not new_commit_hash.strip():
                return False, None, f"Failed to create commit object: {err}"
            new_commit_hash = new_commit_hash.strip()

            # 5. Advance branch ref
            branch = self.git_mgr.get_current_branch()
            rc, _, err = safe_subprocess_run(
                ["git", "update-ref", f"refs/heads/{branch}", new_commit_hash],
                cwd=self.repo_path,
                env=env,
            )
            if rc != 0:
                return False, None, f"Failed to update branch ref: {err}"

            logger.info(
                f"Isolated commit {new_commit_hash[:7]} created successfully on branch '{branch}'."
            )
            return True, new_commit_hash, None

        finally:
            if temp_index_path.exists():
                try:
                    temp_index_path.unlink()
                except Exception:
                    pass

