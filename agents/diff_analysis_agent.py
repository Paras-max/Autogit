"""
Diff Analysis Agent for AutoGit AI.
Parses working directory changes, chunks diffs, filters binaries and generated files,
and produces structured diff intelligence.
"""

from pathlib import Path
from typing import Any, Dict, List, Optional
import fnmatch

from ai.llm_client import BaseLLMClient
from ai.prompt_templates import DIFF_ANALYSIS_SYSTEM_PROMPT
from ai.provider_factory import AIProviderFactory
from ai.response_parser import DiffAnalysisResult, FileChangeItem, extract_json_from_text
from config.constants import DEFAULT_IGNORED_DIRS, DEFAULT_IGNORED_EXTENSIONS
from core.git_manager import GitManager
from utils.logger import logger

# Binary file extensions that should not have diffs processed as text
BINARY_EXTENSIONS = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar",
    ".gz", ".exe", ".dll", ".so", ".bin", ".pyc", ".db", ".sqlite",
}

MAX_DIFF_CHARS_PER_FILE = 8000
MAX_TOTAL_DIFF_CHARS = 30000


class DiffAnalysisAgent:
    """Understands and categorizes Git changes from live diffs."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm_client = llm_client or AIProviderFactory.get_client()

    def is_binary_or_ignored(self, file_path: str) -> bool:
        p = Path(file_path)
        if p.suffix.lower() in BINARY_EXTENSIONS or p.suffix.lower() in DEFAULT_IGNORED_EXTENSIONS:
            return True
        for part in p.parts:
            if part in DEFAULT_IGNORED_DIRS:
                return True
        return False

    def chunk_diff(self, diff_text: str, max_chars: int = MAX_DIFF_CHARS_PER_FILE) -> str:
        """Truncate overly large diffs to avoid LLM context exhaustion."""
        if len(diff_text) <= max_chars:
            return diff_text
        return diff_text[:max_chars] + f"\n... [Diff truncated to {max_chars} characters]"

    def extract_stats_from_diff(self, diff_text: str) -> Dict[str, int]:
        additions = 0
        deletions = 0
        for line in diff_text.splitlines():
            if line.startswith("+") and not line.startswith("+++"):
                additions += 1
            elif line.startswith("-") and not line.startswith("---"):
                deletions += 1
        return {"additions": additions, "deletions": deletions}

    async def analyze_diff(
        self, repo_path: Path | str, target_files: Optional[List[str]] = None
    ) -> DiffAnalysisResult:
        """
        Analyze current working tree modifications in repo_path.
        """
        git_mgr = GitManager(repo_path)
        git_status = git_mgr.get_git_status()
        changes = git_status["changes"]

        # Aggregate all changed file paths
        all_changed_files = set()
        all_changed_files.update(changes.get("modified", []))
        all_changed_files.update(changes.get("untracked", []))
        all_changed_files.update(changes.get("deleted", []))
        all_changed_files.update(changes.get("staged_added", []))
        all_changed_files.update(changes.get("staged_modified", []))
        all_changed_files.update(changes.get("staged_deleted", []))
        all_changed_files.update(changes.get("renamed", []))

        if target_files:
            filtered_files = [f for f in all_changed_files if f in target_files]
        else:
            filtered_files = list(all_changed_files)

        # Exclude ignored/binary files
        filtered_files = [f for f in filtered_files if not self.is_binary_or_ignored(f)]

        if not filtered_files:
            return DiffAnalysisResult(
                summary="No meaningful text file changes detected.",
                files=[],
                total_additions=0,
                total_deletions=0,
            )

        # Build file-by-file diff context
        file_items: List[FileChangeItem] = []
        total_add = 0
        total_del = 0
        diff_context_parts = []

        repo_root = Path(repo_path)

        for rel_file in filtered_files:
            # Determine change type
            if rel_file in changes.get("untracked", []) or rel_file in changes.get("staged_added", []):
                ctype = "CREATED"
            elif rel_file in changes.get("deleted", []) or rel_file in changes.get("staged_deleted", []):
                ctype = "DELETED"
            elif rel_file in changes.get("renamed", []):
                ctype = "RENAMED"
            else:
                ctype = "MODIFIED"

            # Get diff text
            diff_text = git_mgr.get_unstaged_diff(rel_file) or git_mgr.get_staged_diff(rel_file)
            
            # If newly created file and diff is empty, read file content directly
            if ctype == "CREATED" and not diff_text:
                full_path = repo_root / rel_file
                if full_path.exists() and full_path.is_file():
                    try:
                        content = full_path.read_text(encoding="utf-8", errors="replace")
                        diff_text = "\n".join(f"+{line}" for line in content.splitlines())
                    except Exception:
                        diff_text = ""

            stats = self.extract_stats_from_diff(diff_text)
            additions = stats["additions"]
            deletions = stats["deletions"]
            total_add += additions
            total_del += deletions

            is_meaningful = (additions + deletions > 0) or ctype in ("CREATED", "DELETED")

            file_items.append(
                FileChangeItem(
                    file_path=rel_file,
                    change_type=ctype,
                    additions=additions,
                    deletions=deletions,
                    purpose=f"{ctype.capitalize()} {Path(rel_file).name}",
                    is_meaningful=is_meaningful,
                )
            )

            chunked = self.chunk_diff(diff_text)
            diff_context_parts.append(f"--- File: {rel_file} ({ctype}) ---\n{chunked}\n")

        full_diff_text = "\n".join(diff_context_parts)[:MAX_TOTAL_DIFF_CHARS]

        # Call AI for semantic summary
        user_prompt = f"Analyze these repository changes:\n\n{full_diff_text}"
        raw_response = await self.llm_client.generate_response(
            DIFF_ANALYSIS_SYSTEM_PROMPT, user_prompt
        )

        summary = f"Changed {len(file_items)} file(s) (+{total_add}/-{total_del})"
        if raw_response:
            parsed = extract_json_from_text(raw_response)
            if parsed and "summary" in parsed:
                summary = parsed["summary"]

        return DiffAnalysisResult(
            summary=summary,
            files=file_items,
            total_additions=total_add,
            total_deletions=total_del,
        )
