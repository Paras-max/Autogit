"""
Authentication and validation service for GitHub and external providers.
"""

from typing import Any, Dict, Optional
import httpx

from config.constants import (
    AUTH_PROVIDER_GITHUB,
    AUTH_STATUS_INVALID,
    AUTH_STATUS_UNCONFIGURED,
    AUTH_STATUS_VALID,
)
from config.settings import settings
from core.credential_manager import CredentialManager
from database.db import DatabaseManager, db as default_db
from utils.logger import logger
from utils.validators import mask_secret


class AuthenticationService:
    """
    Handles GitHub token validation and authentication status reporting.
    Guarantees secrets are never logged or stored in the database.
    """

    GITHUB_API_URL = "https://api.github.com/user"

    def __init__(
        self,
        database: Optional[DatabaseManager] = None,
        credential_manager: Optional[CredentialManager] = None,
    ):
        self.db = database or default_db
        self.cred_mgr = credential_manager or CredentialManager(self.db)

    async def validate_github_token(
        self, token: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Validate GitHub Personal Access Token against GitHub API (/user endpoint).
        Updates authentication status in SQLite.
        """
        target_token = (token or settings.GITHUB_TOKEN or "").strip()
        if not target_token:
            self.db.upsert_authentication(
                provider=AUTH_PROVIDER_GITHUB,
                authentication_status=AUTH_STATUS_UNCONFIGURED,
                username=None,
            )
            return {
                "success": False,
                "provider": AUTH_PROVIDER_GITHUB,
                "status": AUTH_STATUS_UNCONFIGURED,
                "message": "No GitHub token provided or configured in environment",
            }

        headers = {
            "Authorization": f"Bearer {target_token}",
            "Accept": "application/vnd.github+json",
            "User-Agent": "AutoGit-AI-Phase1",
            "X-GitHub-Api-Version": "2022-11-28",
        }

        masked = mask_secret(target_token)
        logger.info(f"Validating GitHub token ({masked}) against {self.GITHUB_API_URL}")

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.get(self.GITHUB_API_URL, headers=headers)

            if response.status_code == 200:
                data = response.json()
                username = data.get("login")
                user_id = data.get("id")
                user_name = data.get("name")
                html_url = data.get("html_url")

                # Store status in database without token
                self.db.upsert_authentication(
                    provider=AUTH_PROVIDER_GITHUB,
                    authentication_status=AUTH_STATUS_VALID,
                    username=username,
                )
                logger.info(f"GitHub authentication successful for user: {username}")

                return {
                    "success": True,
                    "provider": AUTH_PROVIDER_GITHUB,
                    "status": AUTH_STATUS_VALID,
                    "username": username,
                    "user_info": {
                        "id": user_id,
                        "login": username,
                        "name": user_name,
                        "html_url": html_url,
                    },
                    "token_preview": masked,
                }
            else:
                self.db.upsert_authentication(
                    provider=AUTH_PROVIDER_GITHUB,
                    authentication_status=AUTH_STATUS_INVALID,
                    username=None,
                )
                logger.warning(
                    f"GitHub validation failed with status {response.status_code}"
                )
                return {
                    "success": False,
                    "provider": AUTH_PROVIDER_GITHUB,
                    "status": AUTH_STATUS_INVALID,
                    "status_code": response.status_code,
                    "message": "GitHub API rejected credentials (check token validity and scopes)",
                }
        except httpx.RequestError as e:
            logger.error(f"Network error during GitHub validation: {e}")
            return {
                "success": False,
                "provider": AUTH_PROVIDER_GITHUB,
                "status": AUTH_STATUS_INVALID,
                "message": f"Connection error: {e}",
            }

    def get_overall_auth_status(self) -> Dict[str, Any]:
        """
        Aggregate authentication and provider status without exposing secrets.
        """
        gh_record = self.db.get_authentication(AUTH_PROVIDER_GITHUB)
        ai_status = self.cred_mgr.get_ai_provider_status()
        git_identity = self.cred_mgr.get_git_identity()

        return {
            "github": {
                "status": gh_record.authentication_status if gh_record else AUTH_STATUS_UNCONFIGURED,
                "username": gh_record.username if gh_record else None,
                "last_validated_at": gh_record.last_validated_at if gh_record else None,
                "token_configured": bool(settings.GITHUB_TOKEN and settings.GITHUB_TOKEN.strip()),
                "token_preview": mask_secret(settings.GITHUB_TOKEN),
            },
            "git_identity": git_identity,
            "ai_providers": ai_status,
        }

