"""
Application constants for AutoGit AI.
"""

from typing import Set

# Default directories ignored by file monitoring
DEFAULT_IGNORED_DIRS: Set[str] = {
    ".git",
    "__pycache__",
    "node_modules",
    ".venv",
    "venv",
    "dist",
    "build",
    "logs",
    ".pytest_cache",
    ".mypy_cache",
    ".idea",
    ".vscode",
}

# File extensions or patterns to ignore
DEFAULT_IGNORED_EXTENSIONS: Set[str] = {
    ".pyc",
    ".pyo",
    ".pyd",
    ".swp",
    ".swo",
    ".tmp",
    ".DS_Store",
}

# Event Types for file monitoring
EVENT_CREATED = "CREATED"
EVENT_MODIFIED = "MODIFIED"
EVENT_DELETED = "DELETED"
EVENT_MOVED = "MOVED"

SUPPORTED_EVENT_TYPES = {
    EVENT_CREATED,
    EVENT_MODIFIED,
    EVENT_DELETED,
    EVENT_MOVED,
}

# AI Providers
PROVIDER_OPENAI = "openai"
PROVIDER_ANTHROPIC = "anthropic"
PROVIDER_GEMINI = "gemini"

SUPPORTED_AI_PROVIDERS = {
    PROVIDER_OPENAI,
    PROVIDER_ANTHROPIC,
    PROVIDER_GEMINI,
}

# Auth Providers
AUTH_PROVIDER_GITHUB = "github"

# Auth Status
AUTH_STATUS_VALID = "valid"
AUTH_STATUS_INVALID = "invalid"
AUTH_STATUS_UNCONFIGURED = "unconfigured"

# Event Processed Status
EVENT_STATUS_PENDING = "pending"
EVENT_STATUS_PROCESSED = "processed"
EVENT_STATUS_IGNORED = "ignored"

