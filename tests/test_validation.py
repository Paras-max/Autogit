"""
Tests for Validation Modules (validation/, agents/validation_agent.py).
"""

from pathlib import Path
import pytest

from agents.validation_agent import ValidationAgent
from database.models import RepositoryAutomationSettingsModel
from validation.build_runner import BuildRunner
from validation.lint_runner import LintRunner
from validation.policy_engine import PolicyEngine
from validation.secret_scanner import SecretScanner
from validation.test_runner import TestRunner


def test_secret_scanner_detects_credentials_and_masks_values(tmp_path: Path):
    scanner = SecretScanner()

    # 1. Text containing various secrets
    raw_gh_token = "ghp_1234567890abcdef1234567890abcdef12"
    raw_openai_key = "sk-1234567890abcdef1234567890abcdef"
    raw_aws_key = "AKIA1234567890ABCDEF"
    text = f"""
    GITHUB_TOKEN = "{raw_gh_token}"
    OPENAI = "{raw_openai_key}"
    AWS_KEY = "{raw_aws_key}"
    password = "superSecretPassword123"
    """

    findings = scanner.scan_text(text, file_path="config.py")
    assert len(findings) >= 3

    # CRITICAL SECURITY CHECK: raw secrets MUST NEVER appear in findings
    for f in findings:
        assert raw_gh_token not in f["masked_match"]
        assert raw_openai_key not in f["masked_match"]
        assert "..." in f["masked_match"] or "***" in f["masked_match"]


def test_secret_scanner_detects_forbidden_env_file(tmp_path: Path):
    scanner = SecretScanner()
    env_file = tmp_path / ".env"
    env_file.write_text("SOME_VAR=123\n")

    res = scanner.scan_files(tmp_path, [".env"])
    assert res["has_secrets"] is True
    assert res["findings"][0]["rule_name"] == "Forbidden Environment/Key File"


def test_policy_engine_evaluates_branch_and_secret_violations():
    engine = PolicyEngine()

    settings = RepositoryAutomationSettingsModel(
        repository_id=1,
        execution_mode="auto",
        auto_commit_enabled=True,
        protected_branches=["main", "master"],
    )

    # 1. Blocked on protected branch in auto mode
    res = engine.evaluate_policies(
        current_branch="main",
        files_to_commit=["app.py"],
        total_diff_chars=50,
        secret_findings=[],
        settings=settings,
    )
    assert res["is_valid"] is False
    assert any("protected branch" in v.lower() for v in res["violations"])
    assert res["auto_commit_eligible"] is False

    # 2. Blocked when secrets are present
    res_secret = engine.evaluate_policies(
        current_branch="feature/login",
        files_to_commit=["app.py"],
        total_diff_chars=50,
        secret_findings=[{"rule_name": "API Key"}],
        settings=settings,
    )
    assert res_secret["is_valid"] is False
    assert any("secret" in v.lower() for v in res_secret["violations"])

    # 3. Passed on feature branch without secrets
    res_pass = engine.evaluate_policies(
        current_branch="feature/login",
        files_to_commit=["app.py"],
        total_diff_chars=50,
        secret_findings=[],
        settings=settings,
    )
    assert res_pass["is_valid"] is True
    assert res_pass["auto_commit_eligible"] is True


def test_test_runner_skips_when_no_tests_exist(tmp_path: Path):
    empty_dir = tmp_path / "empty_proj"
    empty_dir.mkdir()

    runner = TestRunner()
    res = runner.run_tests(empty_dir)
    assert res["status"] == "SKIPPED"


def test_validation_agent_overall_report(temp_git_repo: Path):
    agent = ValidationAgent()
    settings = RepositoryAutomationSettingsModel(
        repository_id=1,
        execution_mode="smart",
        auto_commit_enabled=False,
    )

    report = agent.run_all_validations(
        repo_path=temp_git_repo,
        current_branch="feature/test",
        target_files=["README.md"],
        total_diff_chars=20,
        settings=settings,
    )

    assert "overall_status" in report
    assert "secret_scan" in report
    assert "tests" in report
    assert "policies" in report
    assert report["all_passed"] is True

