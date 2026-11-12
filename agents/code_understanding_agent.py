"""
AI Code Understanding Agent for AutoGit AI.
Analyzes relationships, programming languages, intent, risk level, and architectural impact.
"""

from pathlib import Path
from typing import List, Optional

from ai.llm_client import BaseLLMClient
from ai.prompt_templates import CODE_UNDERSTANDING_SYSTEM_PROMPT
from ai.provider_factory import AIProviderFactory
from ai.response_parser import (
    CodeUnderstandingResult,
    DiffAnalysisResult,
    extract_json_from_text,
)
from utils.logger import logger


EXTENSION_LANGUAGE_MAP = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".go": "go",
    ".rs": "rust",
    ".java": "java",
    ".cpp": "cpp",
    ".c": "c",
    ".cs": "csharp",
    ".rb": "ruby",
    ".php": "php",
    ".html": "html",
    ".css": "css",
    ".md": "markdown",
    ".json": "json",
    ".yaml": "yaml",
    ".yml": "yaml",
    ".sql": "sql",
    ".sh": "shell",
}


class CodeUnderstandingAgent:
    """Understands architectural relationships and evaluates risk."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm_client = llm_client or AIProviderFactory.get_client()

    def detect_primary_language(self, file_paths: List[str]) -> str:
        counts = {}
        for f in file_paths:
            ext = Path(f).suffix.lower()
            lang = EXTENSION_LANGUAGE_MAP.get(ext, "other")
            counts[lang] = counts.get(lang, 0) + 1
        if not counts:
            return "unknown"
        return max(counts, key=counts.get)

    async def understand_changes(
        self, diff_result: DiffAnalysisResult
    ) -> CodeUnderstandingResult:
        file_paths = [f.file_path for f in diff_result.files]
        primary_lang = self.detect_primary_language(file_paths)

        if not file_paths:
            return CodeUnderstandingResult(
                change_summary="No changes to analyze.",
                primary_language=primary_lang,
                logical_task="None",
                risk_level="low",
                is_breaking=False,
                requires_validation=False,
                file_purposes={},
            )

        # Build prompt payload
        file_overview = "\n".join(
            f"- {f.file_path} ({f.change_type}): +{f.additions}/-{f.deletions}"
            for f in diff_result.files
        )
        user_prompt = (
            f"Analyze the relationship and architectural intent of these modified files:\n\n"
            f"Summary: {diff_result.summary}\n"
            f"Files:\n{file_overview}"
        )

        raw_response = await self.llm_client.generate_response(
            CODE_UNDERSTANDING_SYSTEM_PROMPT, user_prompt
        )

        if raw_response:
            parsed = extract_json_from_text(raw_response)
            if parsed:
                try:
                    return CodeUnderstandingResult(
                        change_summary=parsed.get("change_summary", diff_result.summary),
                        primary_language=parsed.get("primary_language", primary_lang),
                        logical_task=parsed.get("logical_task", "Codebase Update"),
                        risk_level=parsed.get("risk_level", "low").lower(),
                        is_breaking=bool(parsed.get("is_breaking", False)),
                        requires_validation=bool(parsed.get("requires_validation", True)),
                        file_purposes=parsed.get("file_purposes", {}),
                    )
                except Exception as e:
                    logger.warning(f"Error parsing code understanding result: {e}")

        # Deterministic heuristic fallback
        risk = "medium" if len(file_paths) > 5 or diff_result.total_deletions > 100 else "low"
        return CodeUnderstandingResult(
            change_summary=diff_result.summary,
            primary_language=primary_lang,
            logical_task="Feature or Bugfix Update",
            risk_level=risk,
            is_breaking=False,
            requires_validation=True,
            file_purposes={f: f"Update {Path(f).name}" for f in file_paths},
        )

