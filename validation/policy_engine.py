"""
Policy Engine for AutoGit AI.
Enforces security, branch protection, change thresholds, and Auto Commit rules.
"""

from typing import Any, Dict, List, Optional

from database.models import RepositoryAutomationSettingsModel
from utils.logger import logger


class PolicyEngine:
    """Evaluates safety and governance policies before staging and committing."""

    DEFAULT_MAX_FILES = 50
    DEFAULT_MAX_DIFF_CHARS = 100000

    def evaluate_policies(
        self,
        current_branch: str,
        files_to_commit: List[str],
        total_diff_chars: int,
        secret_findings: List[Dict[str, Any]],
        settings: RepositoryAutomationSettingsModel,
        test_status: str = "SKIPPED",
    ) -> Dict[str, Any]:
        violations = []
        warnings = []

        # 1. Secret Detection Check (CRITICAL - Zero Tolerance)
        if secret_findings:
            violations.append(
                f"Blocked: Detected {len(secret_findings)} secret(s) in proposed changes."
            )

        # 2. Protected Branch Policy
        # Auto Commit is strictly forbidden on protected branches without explicit override
        is_protected_branch = current_branch.lower() in [
            b.lower() for b in settings.protected_branches
        ]
        if is_protected_branch and settings.execution_mode == "auto":
            violations.append(
                f"Auto Commit is forbidden on protected branch '{current_branch}'. Explicit approval required."
            )

        # 3. Maximum Changed Files Threshold
        if len(files_to_commit) > self.DEFAULT_MAX_FILES:
            violations.append(
                f"Changed file count ({len(files_to_commit)}) exceeds maximum threshold of {self.DEFAULT_MAX_FILES}."
            )

        # 4. Maximum Diff Size Threshold
        if total_diff_chars > self.DEFAULT_MAX_DIFF_CHARS:
            violations.append(
                f"Diff size ({total_diff_chars} characters) exceeds safety threshold of {self.DEFAULT_MAX_DIFF_CHARS}."
            )

        # 5. Mandatory Test Policy for Auto Commit
        if settings.validation_required and settings.execution_mode == "auto":
            if test_status == "FAILED":
                violations.append("Mandatory tests failed. Auto Commit blocked.")

        # 6. Check for empty file list
        if not files_to_commit:
            violations.append("Cannot commit empty change set.")

        status = "FAILED" if violations else ("WARNING" if warnings else "PASSED")
        auto_commit_eligible = (
            len(violations) == 0
            and settings.auto_commit_enabled
            and not is_protected_branch
        )

        return {
            "status": status,
            "is_valid": len(violations) == 0,
            "violations": violations,
            "warnings": warnings,
            "is_protected_branch": is_protected_branch,
            "auto_commit_eligible": auto_commit_eligible,
        }

