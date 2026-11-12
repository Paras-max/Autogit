"""
Conflict Detection and Management for AutoGit AI (Phase 4).
Detects merge conflicts non-destructively without modifying developer working directories
or running destructive merge, reset, or rebase operations.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from utils.logger import logger
from utils.security import safe_subprocess_run


class ConflictManager:
    """Non-destructive Git merge conflict detection engine."""

    def check_conflicts(
        self,
        repo_path: Path | str,
        local_branch: str,
        remote_branch: str,
    ) -> Dict[str, Any]:
        """
        Check if merging remote tracking branch into local branch would produce conflicts.
        Uses in-memory 3-way merge-tree checks.
        Never alters the working tree, index, or branch refs.
        """
        repo_path = Path(repo_path).resolve()

        # 1. Verify remote ref exists
        exit_code, _, _ = safe_subprocess_run(
            ["git", "rev-parse", "--verify", remote_branch], cwd=repo_path, timeout=5.0
        )
        if exit_code != 0:
            return {
                "has_conflict": False,
                "is_diverged": False,
                "conflicting_files": [],
                "message": f"Remote ref '{remote_branch}' does not exist.",
            }

        # 2. Check merge-base (common ancestor)
        exit_code_mb, base_stdout, _ = safe_subprocess_run(
            ["git", "merge-base", local_branch, remote_branch], cwd=repo_path, timeout=5.0
        )
        if exit_code_mb != 0 or not base_stdout.strip():
            # Unrelated histories or fresh branch
            return {
                "has_conflict": False,
                "is_diverged": False,
                "conflicting_files": [],
                "message": "No common merge base found (fresh branch).",
            }

        merge_base = base_stdout.strip()

        # 3. Check divergence
        exit_code_ahead, ahead_out, _ = safe_subprocess_run(
            ["git", "rev-list", "--count", f"{remote_branch}..{local_branch}"],
            cwd=repo_path,
            timeout=5.0,
        )
        exit_code_behind, behind_out, _ = safe_subprocess_run(
            ["git", "rev-list", "--count", f"{local_branch}..{remote_branch}"],
            cwd=repo_path,
            timeout=5.0,
        )

        ahead = int(ahead_out.strip()) if exit_code_ahead == 0 and ahead_out.strip().isdigit() else 0
        behind = int(behind_out.strip()) if exit_code_behind == 0 and behind_out.strip().isdigit() else 0
        is_diverged = (ahead > 0 and behind > 0)

        if not is_diverged:
            # Fast-forward possible or strictly ahead/behind; no conflict
            return {
                "has_conflict": False,
                "is_diverged": False,
                "ahead_count": ahead,
                "behind_count": behind,
                "conflicting_files": [],
                "message": "No divergence detected; fast-forward merge possible.",
            }

        # 4. In-memory conflict check via git merge-tree
        # git merge-tree <merge-base> <branch1> <branch2>
        exit_code_mt, mt_stdout, _ = safe_subprocess_run(
            ["git", "merge-tree", merge_base, local_branch, remote_branch],
            cwd=repo_path,
            timeout=10.0,
        )

        conflicting_files: List[str] = []
        if exit_code_mt == 0 and mt_stdout:
            lines = mt_stdout.splitlines()
            current_file = None
            for line in lines:
                if "changed in both" in line or "merged" in line:
                    parts = line.split()
                    if len(parts) >= 3:
                        current_file = parts[-1]
                elif "<<<<<<<" in line or ">>>>>>>" in line:
                    if current_file and current_file not in conflicting_files:
                        conflicting_files.append(current_file)

        has_conflict = len(conflicting_files) > 0 or ("<<<<<<<" in mt_stdout)

        if has_conflict:
            logger.warning(
                f"Conflict detected between '{local_branch}' and '{remote_branch}' in {repo_path.name}: "
                f"{conflicting_files}"
            )
            return {
                "has_conflict": True,
                "is_diverged": True,
                "ahead_count": ahead,
                "behind_count": behind,
                "conflicting_files": conflicting_files,
                "message": (
                    f"Remote branch has diverged with {len(conflicting_files)} conflicting file(s). "
                    "Automatic synchronization halted to preserve local changes. Manual intervention required."
                ),
            }

        return {
            "has_conflict": False,
            "is_diverged": True,
            "ahead_count": ahead,
            "behind_count": behind,
            "conflicting_files": [],
            "message": "Branches have diverged but changes are in disjoint files (clean merge possible).",
        }

