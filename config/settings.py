"""
Application configuration and settings using Pydantic Settings.
"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Base paths
    BASE_DIR: Path = Path(__file__).resolve().parent.parent

    # Environment
    APP_ENV: str = "development"
    LOG_LEVEL: str = "INFO"

    # Database
    DATABASE_PATH: Path = BASE_DIR / "autogit.db"

    # Git Identity overrides (optional)
    GIT_AUTHOR_NAME: Optional[str] = None
    GIT_AUTHOR_EMAIL: Optional[str] = None

    # Credentials (read from environment / .env, never exposed)
    GITHUB_TOKEN: Optional[str] = None
    OPENAI_API_KEY: Optional[str] = None
    ANTHROPIC_API_KEY: Optional[str] = None
    GEMINI_API_KEY: Optional[str] = None
    DEFAULT_AI_PROVIDER: str = "gemini"

    # Monitoring parameters
    DEBOUNCE_INTERVAL_SECONDS: float = 1.0
    GIT_RECONCILIATION_INTERVAL_SECONDS: float = 30.0

    # Phase 3: Scheduler and Autonomous Development
    SCHEDULER_TIMEZONE: str = "Asia/Kolkata"
    SCHEDULER_DAYS_PER_WEEK: int = 5
    SCHEDULER_CATCH_UP_POLICY: str = "single"  # "single", "skip", or "none"
    WORKTREE_BASE_DIR: Path = BASE_DIR / ".autogit_worktrees"
    AUTONOMOUS_BRANCH_PREFIX: str = "autogit/dev"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()

