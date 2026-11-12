"""
Phase 3 Tests: Repository Permission Management and Authorization Enforcement
"""

import pytest
from database.db import DatabaseManager
from database.models import RepositoryPermissionModel
from database.permission_repository import PermissionRepository
from core.permission_manager import PermissionDeniedError, PermissionManager


@pytest.fixture
def mem_db():
    return DatabaseManager(":memory:")


@pytest.fixture
def test_repo(mem_db):
    return mem_db.add_repository(
        name="PermissionTestRepo",
        path="/fake/path",
        remote_url="https://github.com/user/repo",
        current_branch="main",
    )


class TestPermissionRepository:
    def test_get_default_permissions_for_new_repo(self, mem_db, test_repo):
        repo = PermissionRepository(mem_db)
        perms = repo.get_permissions(test_repo.id)
        assert perms.repository_id == test_repo.id
        assert perms.monitoring_enabled is True
        assert perms.ai_analysis_enabled is True
        # Safety defaults – must be disabled
        assert perms.autonomous_development_enabled is False
        assert perms.auto_commit_enabled is False
        assert perms.remote_push_enabled is False

    def test_save_and_retrieve_permissions(self, mem_db, test_repo):
        repo = PermissionRepository(mem_db)
        model = RepositoryPermissionModel(
            repository_id=test_repo.id,
            monitoring_enabled=True,
            ai_analysis_enabled=True,
            autonomous_development_enabled=True,
            smart_commit_enabled=True,
            auto_commit_enabled=False,
            remote_push_enabled=False,
        )
        repo.save_permissions(model)
        retrieved = repo.get_permissions(test_repo.id)
        assert retrieved.autonomous_development_enabled is True

    def test_update_specific_permissions(self, mem_db, test_repo):
        perm_repo = PermissionRepository(mem_db)
        perm_repo.update_permissions(
            test_repo.id,
            autonomous_development_enabled=True,
        )
        perms = perm_repo.get_permissions(test_repo.id)
        assert perms.autonomous_development_enabled is True
        # Other permissions must remain unchanged
        assert perms.auto_commit_enabled is False
        assert perms.remote_push_enabled is False

    def test_revoke_all_permissions(self, mem_db, test_repo):
        perm_repo = PermissionRepository(mem_db)
        perm_repo.revoke_all(test_repo.id)
        perms = perm_repo.get_permissions(test_repo.id)
        assert perms.monitoring_enabled is False
        assert perms.ai_analysis_enabled is False
        assert perms.autonomous_development_enabled is False


class TestPermissionManager:
    def test_verify_permission_monitoring_enabled_by_default(self, mem_db, test_repo):
        pm = PermissionManager(mem_db)
        assert pm.verify_permission(test_repo.id, "monitoring") is True

    def test_verify_autonomous_development_disabled_by_default(self, mem_db, test_repo):
        pm = PermissionManager(mem_db)
        assert pm.verify_permission(test_repo.id, "autonomous_development") is False

    def test_assert_permission_raises_on_unauthorized(self, mem_db, test_repo):
        pm = PermissionManager(mem_db)
        with pytest.raises(PermissionDeniedError):
            pm.assert_permission(test_repo.id, "autonomous_development")

    def test_enable_and_verify_autonomous_development(self, mem_db, test_repo):
        pm = PermissionManager(mem_db)
        pm.enable_autonomous_development(test_repo.id)
        assert pm.verify_permission(test_repo.id, "autonomous_development") is True

    def test_disable_autonomous_development(self, mem_db, test_repo):
        pm = PermissionManager(mem_db)
        pm.enable_autonomous_development(test_repo.id)
        pm.disable_autonomous_development(test_repo.id)
        assert pm.verify_permission(test_repo.id, "autonomous_development") is False

    def test_revoke_all_via_manager(self, mem_db, test_repo):
        pm = PermissionManager(mem_db)
        pm.enable_autonomous_development(test_repo.id)
        pm.revoke_all_permissions(test_repo.id)
        assert pm.verify_permission(test_repo.id, "monitoring") is False
        assert pm.verify_permission(test_repo.id, "autonomous_development") is False

    def test_invalid_repo_raises_value_error(self, mem_db):
        pm = PermissionManager(mem_db)
        with pytest.raises(ValueError):
            pm.get_permissions(99999)

    def test_invalid_permission_name_raises_value_error(self, mem_db, test_repo):
        pm = PermissionManager(mem_db)
        with pytest.raises(ValueError, match="Unknown permission"):
            pm.verify_permission(test_repo.id, "invalid_permission_xyz")

    def test_get_authorized_repositories_filtered_by_permission(self, mem_db, test_repo):
        pm = PermissionManager(mem_db)
        # Add second repo
        repo2 = mem_db.add_repository("Repo2", "/fake/path2", current_branch="main")
        pm.enable_autonomous_development(test_repo.id)
        # Only test_repo should have autonomous_development
        auth_repos = pm.get_authorized_repositories("autonomous_development")
        auth_ids = [r.id for r in auth_repos]
        assert test_repo.id in auth_ids
        assert repo2.id not in auth_ids

