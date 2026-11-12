"""
Phase 3 Tests: Project Analyzer, Task Manager, Development Agent Authorization
"""

import os
import subprocess
import tempfile
from pathlib import Path
import pytest

from database.db import DatabaseManager
from development.project_analyzer import ProjectAnalyzer
from development.task_manager import TaskManager
from core.permission_manager import PermissionDeniedError, PermissionManager
from agents.development_agent import DevelopmentAgent
from development.code_modifier import CodeModifier, CodeModificationError


@pytest.fixture
def mem_db():
    return DatabaseManager(":memory:")


@pytest.fixture
def test_repo(mem_db, tmp_path):
    repo_path = tmp_path / "test_project"
    repo_path.mkdir()
    subprocess.run(["git", "init", str(repo_path)], capture_output=True)
    subprocess.run(
        ["git", "-c", "user.name=Test", "-c", "user.email=test@test.com", "commit", "--allow-empty", "-m", "Init"],
        capture_output=True, cwd=str(repo_path)
    )
    (repo_path / "requirements.txt").write_text("fastapi\npytest\n")
    return mem_db.add_repository(
        name="TestProject",
        path=str(repo_path),
        current_branch="main",
    )


class TestProjectAnalyzer:
    def test_analyze_python_project(self, mem_db, test_repo, tmp_path):
        analyzer = ProjectAnalyzer(mem_db)
        repo = mem_db.get_repository(test_repo.id)
        ctx = analyzer.analyze_repository(test_repo.id, repo.repository_path)
        assert ctx.primary_language == "python"
        assert ctx.repository_id == test_repo.id
        assert ctx.project_type is not None

    def test_detect_fastapi_framework(self, mem_db, test_repo):
        analyzer = ProjectAnalyzer(mem_db)
        repo = mem_db.get_repository(test_repo.id)
        repo_path = Path(repo.repository_path)
        ctx = analyzer.analyze_repository(test_repo.id, repo_path)
        assert ctx.framework == "FastAPI"

    def test_detect_pytest_test_framework(self, mem_db, test_repo):
        analyzer = ProjectAnalyzer(mem_db)
        repo = mem_db.get_repository(test_repo.id)
        ctx = analyzer.analyze_repository(test_repo.id, repo.repository_path)
        assert ctx.test_framework == "pytest"

    def test_get_context_returns_cached_analysis(self, mem_db, test_repo):
        analyzer = ProjectAnalyzer(mem_db)
        repo = mem_db.get_repository(test_repo.id)
        analyzer.analyze_repository(test_repo.id, repo.repository_path)
        ctx = analyzer.get_context(test_repo.id)
        assert ctx is not None
        assert ctx.primary_language == "python"

    def test_get_context_returns_none_when_not_analyzed(self, mem_db, test_repo):
        analyzer = ProjectAnalyzer(mem_db)
        # Repository has NOT been analyzed yet (fresh mem_db)
        fresh_db = DatabaseManager(":memory:")
        fresh_repo = fresh_db.add_repository("New", "/path", current_branch="main")
        analyzer2 = ProjectAnalyzer(fresh_db)
        ctx = analyzer2.get_context(fresh_repo.id)
        assert ctx is None


class TestTaskManager:
    def test_add_task_persisted_in_db(self, mem_db, test_repo):
        tm = TaskManager(mem_db)
        task = tm.add_task(
            repository_id=test_repo.id,
            title="Add error handling",
            description="Improve error handling in utils",
            task_type="refactor",
            priority="high",
        )
        assert task.id is not None
        assert task.status == "pending"
        assert task.priority == "high"

    def test_get_pending_tasks_respects_priority_order(self, mem_db, test_repo):
        tm = TaskManager(mem_db)
        tm.add_task(test_repo.id, "Low task", task_type="feature", priority="low")
        tm.add_task(test_repo.id, "High task", task_type="test", priority="high")
        tm.add_task(test_repo.id, "Medium task", task_type="refactor", priority="medium")
        tasks = tm.get_pending_tasks(test_repo.id)
        assert tasks[0].priority == "high"
        assert tasks[1].priority == "medium"
        assert tasks[2].priority == "low"

    def test_update_task_status_to_completed(self, mem_db, test_repo):
        tm = TaskManager(mem_db)
        task = tm.add_task(test_repo.id, "Test task", priority="medium")
        result = tm.update_task_status(task.id, "completed")
        assert result is True
        updated = tm.get_task(task.id)
        assert updated.status == "completed"
        assert updated.completed_at is not None

    def test_suggest_tasks_when_empty(self, mem_db, test_repo):
        tm = TaskManager(mem_db)
        # No tasks present
        suggested = tm.suggest_tasks_if_empty(test_repo.id)
        assert len(suggested) >= 2
        types = {t.task_type for t in suggested}
        assert "test" in types

    def test_suggest_tasks_does_not_add_when_tasks_exist(self, mem_db, test_repo):
        tm = TaskManager(mem_db)
        tm.add_task(test_repo.id, "Existing task", priority="high")
        suggested = tm.suggest_tasks_if_empty(test_repo.id)
        # Should return existing task, not add more
        assert len(suggested) == 1
        assert suggested[0].title == "Existing task"


class TestCodeModifier:
    def test_apply_new_file_creation(self, mem_db, tmp_path):
        modifier = CodeModifier(mem_db)
        content = 'def hello():\n    return "world"\n'
        change = modifier.apply_file_change(
            base_dir=tmp_path,
            relative_file="utils/helper.py",
            content=content,
            description="Create helper module",
        )
        assert change.change_type == "created"
        assert (tmp_path / "utils" / "helper.py").exists()

    def test_apply_file_modification(self, mem_db, tmp_path):
        (tmp_path / "mod.py").write_text("x = 1\n")
        modifier = CodeModifier(mem_db)
        change = modifier.apply_file_change(
            base_dir=tmp_path,
            relative_file="mod.py",
            content="x = 42\n",
            description="Update constant",
        )
        assert change.change_type == "modified"
        assert (tmp_path / "mod.py").read_text() == "x = 42\n"

    def test_path_traversal_is_blocked(self, mem_db, tmp_path):
        modifier = CodeModifier(mem_db)
        with pytest.raises(CodeModificationError, match="safety policies"):
            modifier.apply_file_change(
                base_dir=tmp_path,
                relative_file="../../etc/passwd",
                content="malicious content",
            )

    def test_forbidden_env_file_blocked(self, mem_db, tmp_path):
        modifier = CodeModifier(mem_db)
        with pytest.raises(CodeModificationError, match="safety policies"):
            modifier.apply_file_change(
                base_dir=tmp_path,
                relative_file=".env",
                content="SECRET=leaked",
            )

    def test_python_syntax_validation_rejects_bad_code(self, mem_db, tmp_path):
        modifier = CodeModifier(mem_db)
        with pytest.raises(CodeModificationError, match="Syntax error"):
            modifier.apply_file_change(
                base_dir=tmp_path,
                relative_file="broken.py",
                content="def foo(\n  no closing bracket here\n",
            )


class TestDevelopmentAgentAuthorization:
    def test_run_session_on_unauthorized_repo_raises_permission_error(self, mem_db, test_repo):
        """DevelopmentAgent must refuse to run on repos without autonomous_development enabled."""
        agent = DevelopmentAgent(database=mem_db)
        with pytest.raises(PermissionDeniedError):
            agent.run_development_session(repository_id=test_repo.id)

    def test_run_session_on_nonexistent_repo_raises_value_error(self, mem_db):
        agent = DevelopmentAgent(database=mem_db)
        with pytest.raises(ValueError):
            agent.run_development_session(repository_id=99999)

    def test_run_session_on_authorized_repo_executes_successfully(self, mem_db, test_repo, tmp_path):
        pm = PermissionManager(mem_db)
        pm.enable_autonomous_development(test_repo.id)
        # Use isolated worktree manager in tmp_path
        from core.worktree_manager import WorktreeManager
        wm = WorktreeManager(base_worktree_dir=tmp_path / "wt")
        agent = DevelopmentAgent(database=mem_db, worktree_mgr=wm)

        result = agent.run_development_session(repository_id=test_repo.id, isolated_worktree=True)
        assert result.status == "completed"
        assert result.repository_id == test_repo.id
        assert len(result.files_modified) >= 1
        assert result.commit_hash is not None
        assert result.branch_name.startswith("autogit/dev-")

