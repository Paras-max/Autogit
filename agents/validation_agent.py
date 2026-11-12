"""
Validation Agent for AutoGit AI.
Coordinates secret scanning, tests, linter, build checks, and policy evaluations.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional

from database.models import RepositoryAutomationSettingsModel
from validation.build_runner import BuildRunner
from validation.lint_runner import LintRunner
from validation.policy_engine import PolicyEngine
from validation.secret_scanner import SecretScanner
from validation.test_runner import TestRunner


class ValidationAgent:
    """Orchestrates comprehensive pre-commit verification."""

    def __init__(
        self,
        secret_scanner: Optional[SecretScanner] = None,
        test_runner: Optional[TestRunner] = None,
        lint_runner: Optional[LintRunner] = None,
        build_runner: Optional[BuildRunner] = None,
        policy_engine: Optional[PolicyEngine] = None,
    ):
        self.secret_scanner = secret_scanner or SecretScanner()
        self.test_runner = test_runner or TestRunner()
        self.lint_runner = lint_runner or LintRunner()
        self.build_runner = build_runner or BuildRunner()
        self.policy_engine = policy_engine or PolicyEngine()

    def run_all_validations(
        self,
        repo_path: Path | str,
        current_branch: str,
        target_files: List[str],
        total_diff_chars: int,
        settings: RepositoryAutomationSettingsModel,
    ) -> Dict[str, Any]:
        path = Path(repo_path).resolve()

        # 1. Secret Scanning (Mandatory)
        secret_res = self.secret_scanner.scan_files(path, target_files)

        # 2. Test Execution
        test_res = self.test_runner.run_tests(path)

        # 3. Lint Execution
        lint_res = self.lint_runner.run_lint(path)

        # 4. Build Execution
        build_res = self.build_runner.run_build(path)

        # 5. Policy Evaluation
        policy_res = self.policy_engine.evaluate_policies(
            current_branch=current_branch,
            files_to_commit=target_files,
            total_diff_chars=total_diff_chars,
            secret_findings=secret_res["findings"],
            settings=settings,
            test_status=test_res["status"],
        )

        all_passed = (
            not secret_res["has_secrets"]
            and test_res["status"] != "FAILED"
            and build_res["status"] != "FAILED"
            and policy_res["is_valid"]
        )

        overall_status = "PASSED" if all_passed else "FAILED"

        return {
            "overall_status": overall_status,
            "all_passed": all_passed,
            "secret_scan": secret_res,
            "tests": test_res,
            "lint": lint_res,
            "build": build_res,
            "policies": policy_res,
        }

