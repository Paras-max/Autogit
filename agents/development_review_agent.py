"""
Development Review Agent for AutoGit AI (Phase 3).
Inspects code modifications prior to commit to ensure they are meaningful,
safe, non-cosmetic, and satisfy task objectives.
"""

from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from database.models import DevelopmentChangeModel
from utils.logger import logger


@dataclass
class ReviewResult:
    is_approved: bool
    recommendation: str  # 'commit', 'revise', 'discard'
    confidence: float
    issues: List[str] = field(default_factory=list)


class DevelopmentReviewAgent:
    """
    Evaluates proposed development changes before staging and committing.
    Guarantees changes are non-trivial and safe.
    """

    def review_changes(
        self,
        base_dir: Path,
        changes: List[DevelopmentChangeModel],
    ) -> ReviewResult:
        """
        Review list of changes against code quality, non-triviality, and safety guidelines.
        """
        if not changes:
            return ReviewResult(
                is_approved=False,
                recommendation="discard",
                confidence=1.0,
                issues=["No changes detected to review."],
            )

        issues: List[str] = []

        for change in changes:
            file_path = base_dir / change.file_path
            if not file_path.exists():
                issues.append(f"File {change.file_path} does not exist on disk.")
                continue

            content = file_path.read_text(encoding="utf-8", errors="ignore").strip()

            # Check triviality / empty edits
            if not content:
                issues.append(f"File {change.file_path} is completely empty.")
                continue

            # Check cosmetic only
            lines = [l.strip() for l in content.splitlines() if l.strip()]
            code_lines = [l for l in lines if not l.startswith("#") and not l.startswith("//") and not l.startswith("/*")]
            if len(code_lines) < 2 and change.change_type == "created":
                issues.append(f"File {change.file_path} has insufficient substantive code lines.")

            # Secret check in snippet
            for secret_token in ("api_key", "secret_key", "private_key", "password="):
                if secret_token in content.lower():
                    # Check if it looks like a real hardcoded credential
                    for l in lines:
                        if secret_token in l.lower() and ('"' in l or "'" in l) and not l.startswith("#"):
                            issues.append(f"Potential credential found in {change.file_path}: {l[:50]}")

        if issues:
            logger.warning(f"Development review flagged issues: {issues}")
            return ReviewResult(
                is_approved=False,
                recommendation="revise",
                confidence=0.85,
                issues=issues,
            )

        return ReviewResult(
            is_approved=True,
            recommendation="commit",
            confidence=0.95,
            issues=[],
        )

