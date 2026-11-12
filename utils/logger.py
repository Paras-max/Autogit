"""
Structured application logger with sensitive data masking.
"""

import logging
import re
import sys
from pathlib import Path
from typing import Optional


# Patterns for sensitive data that should be redacted
SENSITIVE_PATTERNS = [
    (re.compile(r"(ghp_[A-Za-z0-9_]{30,})", re.IGNORECASE), "[REDACTED_GH_TOKEN]"),
    (re.compile(r"(github_pat_[A-Za-z0-9_]{30,})", re.IGNORECASE), "[REDACTED_GH_PAT]"),
    (re.compile(r"(sk-[A-Za-z0-9_-]{20,})", re.IGNORECASE), "[REDACTED_API_KEY]"),
    (re.compile(r"(AIza[0-9A-Za-z-_]{35})", re.IGNORECASE), "[REDACTED_GEMINI_KEY]"),
    (re.compile(r"(bearer\s+)([A-Za-z0-9_\-\.]{10,})", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(token[:=]\s*)(['\"]?[A-Za-z0-9_\-]{8,}['\"]?)", re.IGNORECASE), r"\1[REDACTED_TOKEN]"),
    (re.compile(r"(password[:=]\s*)(['\"]?[^'\s]+['\"]?)", re.IGNORECASE), r"\1[REDACTED_PASSWORD]"),
]


class RedactingFormatter(logging.Formatter):
    """Formatter that redacts sensitive values like tokens and keys."""

    def format(self, record: logging.LogRecord) -> str:
        msg = super().format(record)
        for pattern, replacement in SENSITIVE_PATTERNS:
            msg = pattern.sub(replacement, msg)
        return msg


def setup_logger(
    name: str = "autogit",
    log_dir: Optional[Path] = None,
    level: str = "INFO",
) -> logging.Logger:
    """
    Set up and configure structured logger for AutoGit AI.
    """
    logger = logging.getLogger(name)
    logger.setLevel(getattr(logging, level.upper(), logging.INFO))

    # Avoid duplicate handlers if already configured
    if logger.handlers:
        return logger

    formatter = RedactingFormatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # Console Handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)

    # File Handler
    if log_dir is None:
        log_dir = Path(__file__).resolve().parent.parent / "logs"

    try:
        log_dir.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_dir / "autogit.log", encoding="utf-8")
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
    except Exception as e:
        logger.warning(f"Failed to create file logger in {log_dir}: {e}")

    logger.propagate = False
    return logger


# Default application-wide logger
logger = setup_logger()

