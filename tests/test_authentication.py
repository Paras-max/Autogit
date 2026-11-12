"""
Tests for Authentication and Credential Management (core/authentication.py, core/credential_manager.py).
"""

from unittest.mock import AsyncMock, patch
import httpx
import pytest

from config.constants import AUTH_STATUS_INVALID, AUTH_STATUS_VALID, PROVIDER_GEMINI, PROVIDER_OPENAI
from core.authentication import AuthenticationService
from core.credential_manager import CredentialManager
from database.db import DatabaseManager
from utils.validators import mask_secret


@pytest.mark.asyncio
async def test_github_token_validation_success_mocked(temp_db: DatabaseManager):
    """Test successful GitHub token validation using mocked response."""
    auth_service = AuthenticationService(database=temp_db)

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 200
    mock_response.json.return_value = {
        "login": "octocat",
        "id": 583231,
        "name": "The Octocat",
        "html_url": "https://github.com/octocat",
    }

    dummy_token = "ghp_1234567890abcdef1234567890abcdef12"

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result = await auth_service.validate_github_token(dummy_token)

    assert result["success"] is True
    assert result["status"] == AUTH_STATUS_VALID
    assert result["username"] == "octocat"
    assert result["user_info"]["id"] == 583231

    # Verify complete token is NEVER in response
    assert dummy_token not in str(result)
    assert result["token_preview"] == "ghp...ef12"

    # Verify DB record contains status and username but NEVER raw token
    stored_auth = temp_db.get_authentication("github")
    assert stored_auth is not None
    assert stored_auth.authentication_status == AUTH_STATUS_VALID
    assert stored_auth.username == "octocat"


@pytest.mark.asyncio
async def test_github_token_validation_failure_mocked(temp_db: DatabaseManager):
    """Test failed GitHub token validation when GitHub returns 401."""
    auth_service = AuthenticationService(database=temp_db)

    mock_response = AsyncMock(spec=httpx.Response)
    mock_response.status_code = 401
    mock_response.json.return_value = {"message": "Bad credentials"}

    bad_token = "ghp_invalidtoken1234567890abcdef"

    with patch("httpx.AsyncClient.get", return_value=mock_response):
        result = await auth_service.validate_github_token(bad_token)

    assert result["success"] is False
    assert result["status"] == AUTH_STATUS_INVALID
    assert bad_token not in str(result)

    stored_auth = temp_db.get_authentication("github")
    assert stored_auth is not None
    assert stored_auth.authentication_status == AUTH_STATUS_INVALID
    assert stored_auth.username is None


def test_ai_provider_selection_and_status(temp_db: DatabaseManager):
    cred_mgr = CredentialManager(database=temp_db)

    # Default is gemini
    assert cred_mgr.get_active_ai_provider() == PROVIDER_GEMINI

    # Switch to openai
    updated = cred_mgr.set_active_ai_provider(PROVIDER_OPENAI)
    assert updated == PROVIDER_OPENAI
    assert cred_mgr.get_active_ai_provider() == PROVIDER_OPENAI

    # Invalid provider raises ValueError
    with pytest.raises(ValueError, match="Unsupported AI provider"):
        cred_mgr.set_active_ai_provider("unknown_ai")

    # Status never exposes raw keys
    status = cred_mgr.get_ai_provider_status()
    assert status["active_provider"] == PROVIDER_OPENAI
    for prov, data in status["providers"].items():
        assert "masked_key" in data
        assert "is_active" in data


def test_mask_secret():
    assert mask_secret(None) is None
    assert mask_secret("") is None
    assert mask_secret("short") == "***"
    assert mask_secret("ghp_1234567890abcdef") == "ghp...cdef"
    assert mask_secret("sk-proj-1234567890abcdef1234") == "sk-...1234"


def test_git_identity_override(temp_db: DatabaseManager):
    cred_mgr = CredentialManager(database=temp_db)

    # Set valid override
    override = cred_mgr.set_git_identity_override("John Doe", "john@example.com")
    assert override["name"] == "John Doe"
    assert override["email"] == "john@example.com"

    # Invalid email raises ValueError
    with pytest.raises(ValueError, match="Invalid email format"):
        cred_mgr.set_git_identity_override("Jane Doe", "invalid-email")

