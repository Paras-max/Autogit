"""
Pytest configuration and fixtures.
"""

from pathlib import Path
import git
import pytest
from fastapi.testclient import TestClient

from api.execution_routes import get_controller, get_exec_repo
from api.routes import get_auth_service, get_cred_manager, get_db, get_monitor, get_repo_manager
from core.authentication import AuthenticationService
from core.credential_manager import CredentialManager
from core.execution_controller import ExecutionController
from core.git_manager import GitManager
from core.repository_manager import RepositoryManager
from database.db import DatabaseManager
from database.execution_repository import ExecutionRepository
from main import app
from monitoring.file_monitor import FileMonitor


@pytest.fixture
def temp_db(tmp_path: Path):
    """Provides a fresh isolated SQLite database instance for tests."""
    db_file = tmp_path / "test_autogit.db"
    db_instance = DatabaseManager(db_path=db_file)
    return db_instance


@pytest.fixture
def temp_git_repo(tmp_path: Path):
    """
    Creates an isolated temporary Git repository with an initial commit.
    """
    repo_dir = tmp_path / "sample_git_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    repo = git.Repo.init(str(repo_dir))

    # Configure local user for the test repo
    with repo.config_writer() as config:
        config.set_value("user", "name", "Test User")
        config.set_value("user", "email", "testuser@example.com")

    # Initial file and commit
    readme = repo_dir / "README.md"
    readme.write_text("# Sample Project\nInitial content\n", encoding="utf-8")
    repo.index.add(["README.md"])
    repo.index.commit("Initial commit")

    return repo_dir


@pytest.fixture
def temp_git_repo_unborn(tmp_path: Path):
    """
    Creates a fresh empty Git repository with no commits (unborn branch).
    """
    repo_dir = tmp_path / "empty_git_repo"
    repo_dir.mkdir(parents=True, exist_ok=True)
    git.Repo.init(str(repo_dir))
    return repo_dir


@pytest.fixture
def test_client(temp_db, temp_git_repo):
    """
    Provides FastAPI TestClient wired to isolated DB and controller.
    """
    test_cred_mgr = CredentialManager(database=temp_db)
    test_repo_mgr = RepositoryManager(database=temp_db)
    test_auth_service = AuthenticationService(database=temp_db, credential_manager=test_cred_mgr)
    test_monitor = FileMonitor(database=temp_db)
    test_exec_repo = ExecutionRepository(database=temp_db)
    test_controller = ExecutionController(database=temp_db, exec_repo=test_exec_repo)

    app.dependency_overrides[get_db] = lambda: temp_db
    app.dependency_overrides[get_cred_manager] = lambda: test_cred_mgr
    app.dependency_overrides[get_repo_manager] = lambda: test_repo_mgr
    app.dependency_overrides[get_auth_service] = lambda: test_auth_service
    app.dependency_overrides[get_monitor] = lambda: test_monitor
    app.dependency_overrides[get_exec_repo] = lambda: test_exec_repo
    app.dependency_overrides[get_controller] = lambda: test_controller

    with TestClient(app) as client:
        yield client

    test_monitor.stop_all()
    app.dependency_overrides.clear()
