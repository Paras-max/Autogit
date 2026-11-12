"""
AI Commit Message Generator for AutoGit AI.
Generates Conventional Commit messages based on actual diffs and code understanding.
"""

from pathlib import Path
from typing import List, Optional

from ai.llm_client import BaseLLMClient
from ai.prompt_templates import COMMIT_MESSAGE_SYSTEM_PROMPT
from ai.provider_factory import AIProviderFactory
from ai.response_parser import (
    CodeUnderstandingResult,
    CommitMessageResult,
    DiffAnalysisResult,
    extract_json_from_text,
)
from utils.logger import logger


class CommitMessageAgent:
    """Generates concise, accurate Conventional Commit messages."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm_client = llm_client or AIProviderFactory.get_client()

    def generate_fallback_message(
        self, files: List[str], diff_summary: str, understanding: Optional[CodeUnderstandingResult] = None
    ) -> CommitMessageResult:
        """
        Deterministic, accurate conventional commit fallback if LLM is unavailable.
        """
        # Determine likely type and scope from files
        ctype = "feat"
        scope = None

        if files:
            first_path = Path(files[0])
            ext = first_path.suffix.lower()
            if ext in [".md", ".rst", ".txt"]:
                ctype = "docs"
                scope = first_path.stem
            elif "test" in first_path.name.lower() or "tests" in [p.lower() for p in first_path.parts]:
                ctype = "test"
                scope = first_path.stem.replace("test_", "").replace("_test", "") or "core"
            elif any(kw in diff_summary.lower() for kw in ["fix", "bug", "error", "resolve"]):
                ctype = "fix"
                scope = first_path.stem
            else:
                scope = first_path.stem

        if len(files) == 1:
            subject = f"update {Path(files[0]).name}"
        elif len(files) <= 3:
            names = ", ".join(Path(f).name for f in files)
            subject = f"update {names}"
        else:
            subject = f"implement {understanding.logical_task if understanding else 'updates'}"

        subject = subject[:70].strip()
        full_msg = f"{ctype}({scope}): {subject}" if scope else f"{ctype}: {subject}"
        body = f"Affected files:\n" + "\n".join(f"- {f}" for f in files)
        full_with_body = f"{full_msg}\n\n{body}"

        return CommitMessageResult(
            commit_type=ctype,
            scope=scope,
            subject=subject,
            body=body,
            full_message=full_with_body,
        )

    async def generate_commit_message(
        self,
        files: List[str],
        diff_result: DiffAnalysisResult,
        understanding: CodeUnderstandingResult,
        user_hint: Optional[str] = None,
    ) -> CommitMessageResult:
        if not files:
            return CommitMessageResult(
                commit_type="chore",
                scope=None,
                subject="no changes",
                body=None,
                full_message="chore: no changes",
            )

        file_list_str = "\n".join(f"- {f}" for f in files)
        user_prompt = (
            f"Generate a Conventional Commit message for these specific files:\n\n"
            f"Target Files:\n{file_list_str}\n\n"
            f"Diff Summary: {diff_result.summary}\n"
            f"Task Context: {understanding.logical_task} ({understanding.change_summary})\n"
        )
        if user_hint:
            user_prompt += f"User Provided Context: {user_hint}\n"

        raw_response = await self.llm_client.generate_response(
            COMMIT_MESSAGE_SYSTEM_PROMPT, user_prompt
        )

        if raw_response:
            parsed = extract_json_from_text(raw_response)
            if parsed and "subject" in parsed and parsed["subject"].strip():
                ctype = parsed.get("commit_type", "feat").lower().strip()
                scope = parsed.get("scope")
                if scope:
                    scope = str(scope).strip().lower()
                subj = parsed["subject"].strip().replace("\n", " ")
                if len(subj) > 72:
                    subj = subj[:72].strip()

                body = parsed.get("body")
                header = f"{ctype}({scope}): {subj}" if scope else f"{ctype}: {subj}"
                full_msg = f"{header}\n\n{body.strip()}" if body and body.strip() else header

                return CommitMessageResult(
                    commit_type=ctype,
                    scope=scope,
                    subject=subj,
                    body=body.strip() if body else None,
                    full_message=full_msg,
                )

        logger.info("Using deterministic Conventional Commit fallback.")
        return self.generate_fallback_message(files, diff_result.summary, understanding)

