"""
GitHub API client for AutoGit AI (Phase 4).
Interacts with GitHub REST API: user profile, rate limits, user repositories,
and credential validation without ever exposing raw tokens in logs or responses.
"""

from typing import Any, Dict, List, Optional, Tuple
import httpx

from config.constants import (
    AUTH_PROVIDER_GITHUB,
    AUTH_STATUS_INVALID,
    AUTH_STATUS_UNCONFIGURED,
    AUTH_STATUS_VALID,
)
from config.settings import settings
from core.authentication import AuthenticationService
from core.credential_manager import CredentialManager
from database.db import DatabaseManager, db as default_db
from utils.logger import logger
from utils.validators import mask_secret


class GitHubClient:
    """Interacts with GitHub REST API and manages authentication state."""

    BASE_URL = "https://api.github.com"

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        cred_manager: Optional[CredentialManager] = None,
        auth_service: Optional[AuthenticationService] = None,
    ):
        self.db = database or default_db
        self.cred_mgr = cred_manager or CredentialManager(self.db)
        self.auth_service = auth_service or AuthenticationService(self.db, self.cred_mgr)

    def _get_token(self, token_override: Optional[str] = None) -> Optional[str]:
        """Retrieve token from override, settings, or credentials securely."""
        t = (token_override or settings.GITHUB_TOKEN or "").strip()
        return t if t else None

    def _build_headers(self, token: str) -> Dict[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "AutoGit-AI",
        }

    async def get_account_info(
        self, token_override: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Fetch authenticated GitHub account profile, rate limit, and authentication status.
        Never returns the raw token.
        """
        token = self._get_token(token_override)
        if not token:
            return {
                "authenticated": False,
                "status": AUTH_STATUS_UNCONFIGURED,
                "user": None,
                "token_preview": None,
                "rate_limit": None,
            }

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.get(
                    f"{self.BASE_URL}/user", headers=self._build_headers(token)
                )
                if res.status_code == 200:
                    data = res.json()
                    user_profile = {
                        "id": data.get("id"),
                        "login": data.get("login"),
                        "name": data.get("name"),
                        "avatar_url": data.get("avatar_url"),
                        "html_url": data.get("html_url"),
                        "public_repos": data.get("public_repos", 0),
                        "total_private_repos": data.get("total_private_repos", 0),
                        "followers": data.get("followers", 0),
                        "following": data.get("following", 0),
                    }
                    rate_limit = await self.get_rate_limit(token)
                    return {
                        "authenticated": True,
                        "status": AUTH_STATUS_VALID,
                        "user": user_profile,
                        "id": user_profile["id"],
                        "login": user_profile["login"],
                        "name": user_profile["name"],
                        "avatar_url": user_profile["avatar_url"],
                        "html_url": user_profile["html_url"],
                        "public_repos": user_profile["public_repos"],
                        "total_private_repos": user_profile["total_private_repos"],
                        "followers": user_profile["followers"],
                        "following": user_profile["following"],
                        "token_preview": mask_secret(token),
                        "rate_limit": rate_limit,
                        "rate_limit_limit": rate_limit.get("limit", 5000),
                        "rate_limit_remaining": rate_limit.get("remaining", 5000),
                        "rate_limit_reset": rate_limit.get("reset", 0),
                    }
                else:
                    return {
                        "authenticated": False,
                        "status": AUTH_STATUS_INVALID,
                        "user": None,
                        "token_preview": mask_secret(token),
                        "rate_limit": None,
                        "error": f"GitHub returned HTTP {res.status_code}",
                    }
            except Exception as e:
                logger.error(f"Failed to communicate with GitHub API: {e}")
                return {
                    "authenticated": False,
                    "status": AUTH_STATUS_INVALID,
                    "user": None,
                    "token_preview": mask_secret(token),
                    "rate_limit": None,
                    "error": str(e),
                }

    async def get_rate_limit(self, token: Optional[str] = None) -> Dict[str, Any]:
        """Fetch current GitHub API rate limit status."""
        tok = self._get_token(token)
        if not tok:
            return {"limit": 60, "remaining": 60, "reset": 0}

        async with httpx.AsyncClient(timeout=10.0) as client:
            try:
                res = await client.get(
                    f"{self.BASE_URL}/rate_limit", headers=self._build_headers(tok)
                )
                if res.status_code == 200:
                    data = res.json()
                    core = data.get("resources", {}).get("core", {})
                    return {
                        "limit": core.get("limit", 5000),
                        "remaining": core.get("remaining", 5000),
                        "reset": core.get("reset", 0),
                    }
            except Exception as e:
                logger.debug(f"Could not retrieve GitHub rate limit: {e}")
        return {"limit": 5000, "remaining": 5000, "reset": 0}

    async def list_repositories(
        self, per_page: int = 30, token_override: Optional[str] = None
    ) -> List[Dict[str, Any]]:
        """Fetch list of user repositories from GitHub API."""
        token = self._get_token(token_override)
        if not token:
            return []

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                res = await client.get(
                    f"{self.BASE_URL}/user/repos?sort=updated&per_page={per_page}",
                    headers=self._build_headers(token),
                )
                if res.status_code == 200:
                    repos = res.json()
                    return [
                        {
                            "id": r.get("id"),
                            "name": r.get("name"),
                            "full_name": r.get("full_name"),
                            "private": r.get("private", False),
                            "html_url": r.get("html_url"),
                            "clone_url": r.get("clone_url"),
                            "ssh_url": r.get("ssh_url"),
                            "default_branch": r.get("default_branch", "main"),
                            "description": r.get("description"),
                            "updated_at": r.get("updated_at"),
                            "pushed_at": r.get("pushed_at"),
                        }
                        for r in repos
                    ]
            except Exception as e:
                logger.error(f"Failed to list GitHub repositories: {e}")
        return []

    def disconnect_account(self) -> bool:
        """Disconnect GitHub credentials and mark authentication unconfigured."""
        self.db.upsert_authentication(
            provider=AUTH_PROVIDER_GITHUB,
            authentication_status=AUTH_STATUS_UNCONFIGURED,
            username=None,
        )
        logger.info("GitHub account disconnected from AutoGit AI.")
        return True

