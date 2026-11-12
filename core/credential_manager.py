"""
Secure credential management for Git identity and AI providers.
Ensures API keys and tokens are never logged or exposed in raw form.
"""

from typing import Any, Dict, Optional
import git

from config.constants import (
    AUTH_PROVIDER_GITHUB,
    PROVIDER_ANTHROPIC,
    PROVIDER_GEMINI,
    PROVIDER_OPENAI,
    SUPPORTED_AI_PROVIDERS,
)
from config.settings import settings
from database.db import DatabaseManager, db as default_db
from utils.logger import logger
from utils.validators import mask_secret, validate_email


class CredentialManager:
    """
    Manages provider configuration, active AI provider selection,
    and Git author identity without exposing secrets.
    """

    def __init__(self, database: Optional[DatabaseManager] = None):
        self.db = database or default_db

    # --- Git Identity ---

    def get_git_identity(self, repo_path: Optional[str] = None) -> Dict[str, Optional[str]]:
        """
        Read existing Git identity (name, email) from repo or global Git config
        without overwriting existing system configuration.
        """
        name = settings.GIT_AUTHOR_NAME
        email = settings.GIT_AUTHOR_EMAIL

        # If not provided in settings, read from Git config
        try:
            if repo_path:
                repo = git.Repo(repo_path)
                reader = repo.config_reader()
            else:
                reader = git.GitConfigParser(
                    [git.GitConfigParser.config_level_paths("global")[0]],
                    read_only=True,
                )

            if not name:
                name = reader.get_value("user", "name", fallback=None)
            if not email:
                email = reader.get_value("user", "email", fallback=None)
        except Exception as e:
            logger.debug(f"Could not read Git config identity: {e}")

        return {
            "name": name,
            "email": email,
        }

    def set_git_identity_override(
        self, name: str, email: str
    ) -> Dict[str, str]:
        """
        Configure Git identity override stored in application settings.
        Does not mutate user's system-level git configuration.
        """
        if not name or not name.strip():
            raise ValueError("Git author name cannot be empty")
        if not email or not validate_email(email):
            raise ValueError(f"Invalid email format: {email}")

        self.db.set_setting("git_author_name", name.strip())
        self.db.set_setting("git_author_email", email.strip())
        logger.info(f"Updated application Git identity override for {email.strip()}")
        return {"name": name.strip(), "email": email.strip()}

    # --- AI Provider Configuration ---

    def get_active_ai_provider(self) -> str:
        """Get the currently selected AI provider."""
        setting = self.db.get_setting("selected_ai_provider")
        if setting and setting.setting_value in SUPPORTED_AI_PROVIDERS:
            return setting.setting_value
        return settings.DEFAULT_AI_PROVIDER

    def set_active_ai_provider(self, provider: str) -> str:
        """Select active AI provider."""
        norm_provider = provider.strip().lower()
        if norm_provider not in SUPPORTED_AI_PROVIDERS:
            raise ValueError(
                f"Unsupported AI provider: {provider}. Supported: {sorted(SUPPORTED_AI_PROVIDERS)}"
            )
        self.db.set_setting("selected_ai_provider", norm_provider)
        logger.info(f"Active AI provider switched to: {norm_provider}")
        return norm_provider

    def get_ai_provider_status(self) -> Dict[str, Any]:
        """
        Return the configuration presence of supported AI providers.
        NEVER returns actual API keys; only masked previews and availability booleans.
        """
        active_provider = self.get_active_ai_provider()

        providers = {
            PROVIDER_GEMINI: {
                "name": "Google Gemini",
                "configured": bool(settings.GEMINI_API_KEY and settings.GEMINI_API_KEY.strip()),
                "masked_key": mask_secret(settings.GEMINI_API_KEY),
                "is_active": active_provider == PROVIDER_GEMINI,
            },
            PROVIDER_OPENAI: {
                "name": "OpenAI",
                "configured": bool(settings.OPENAI_API_KEY and settings.OPENAI_API_KEY.strip()),
                "masked_key": mask_secret(settings.OPENAI_API_KEY),
                "is_active": active_provider == PROVIDER_OPENAI,
            },
            PROVIDER_ANTHROPIC: {
                "name": "Anthropic",
                "configured": bool(settings.ANTHROPIC_API_KEY and settings.ANTHROPIC_API_KEY.strip()),
                "masked_key": mask_secret(settings.ANTHROPIC_API_KEY),
                "is_active": active_provider == PROVIDER_ANTHROPIC,
            },
        }

        return {
            "active_provider": active_provider,
            "providers": providers,
        }

