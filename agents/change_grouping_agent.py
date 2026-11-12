"""
Change Grouping Agent for AutoGit AI.
Identifies logical tasks and organizes changed files into cohesive commit groups.
"""

from pathlib import Path
from typing import List, Optional

from ai.llm_client import BaseLLMClient
from ai.prompt_templates import CHANGE_GROUPING_SYSTEM_PROMPT
from ai.provider_factory import AIProviderFactory
from ai.response_parser import (
    ChangeGroupingResult,
    CodeUnderstandingResult,
    DiffAnalysisResult,
    GroupItem,
    extract_json_from_text,
)
from utils.logger import logger


class ChangeGroupingAgent:
    """Groups related modified files into atomic logical tasks."""

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm_client = llm_client or AIProviderFactory.get_client()

    def heuristic_grouping(self, file_paths: List[str]) -> List[GroupItem]:
        """
        Fallback grouping by directory domain or file type if AI service is offline.
        """
        if not file_paths:
            return []

        doc_files = []
        test_files = []
        code_files = []

        for f in file_paths:
            p = Path(f)
            if p.suffix.lower() in [".md", ".rst", ".txt", ".doc"]:
                doc_files.append(f)
            elif "test" in p.name.lower() or "tests" in [part.lower() for part in p.parts]:
                test_files.append(f)
            else:
                code_files.append(f)

        groups = []
        if code_files:
            groups.append(
                GroupItem(
                    group_name="Core Implementation",
                    explanation="Source code modifications",
                    confidence=0.85,
                    file_list=code_files,
                )
            )
        if test_files:
            groups.append(
                GroupItem(
                    group_name="Testing",
                    explanation="Test suite updates",
                    confidence=0.90,
                    file_list=test_files,
                )
            )
        if doc_files:
            groups.append(
                GroupItem(
                    group_name="Documentation",
                    explanation="Documentation improvements",
                    confidence=0.95,
                    file_list=doc_files,
                )
            )

        # If everything fell into one or none, ensure all files covered
        if not groups:
            groups.append(
                GroupItem(
                    group_name="General Updates",
                    explanation="Cohesive project updates",
                    confidence=0.8,
                    file_list=file_paths,
                )
            )
        return groups

    async def group_changes(
        self, diff_result: DiffAnalysisResult, understanding: CodeUnderstandingResult
    ) -> ChangeGroupingResult:
        file_paths = [f.file_path for f in diff_result.files]
        if not file_paths:
            return ChangeGroupingResult(groups=[])

        # If only 1 or 2 files, keep in one group
        if len(file_paths) <= 2:
            return ChangeGroupingResult(
                groups=[
                    GroupItem(
                        group_name=understanding.logical_task or "Feature Update",
                        explanation="Changes belong to a single focused task",
                        confidence=0.95,
                        file_list=file_paths,
                    )
                ]
            )

        file_list_str = "\n".join(f"- {f}" for f in file_paths)
        user_prompt = (
            f"Group these modified files into logical tasks:\n\n"
            f"Context: {understanding.change_summary} ({understanding.logical_task})\n"
            f"Files:\n{file_list_str}"
        )

        raw_response = await self.llm_client.generate_response(
            CHANGE_GROUPING_SYSTEM_PROMPT, user_prompt
        )

        if raw_response:
            parsed = extract_json_from_text(raw_response)
            if parsed and "groups" in parsed and isinstance(parsed["groups"], list):
                valid_groups = []
                covered_files = set()
                for g in parsed["groups"]:
                    flist = [f for f in g.get("file_list", []) if f in file_paths]
                    if flist:
                        valid_groups.append(
                            GroupItem(
                                group_name=g.get("group_name", "Task"),
                                explanation=g.get("explanation", ""),
                                confidence=float(g.get("confidence", 0.9)),
                                file_list=flist,
                            )
                        )
                        covered_files.update(flist)

                # Ensure any unassigned files are added
                unassigned = [f for f in file_paths if f not in covered_files]
                if unassigned:
                    if valid_groups:
                        valid_groups[0].file_list.extend(unassigned)
                    else:
                        valid_groups.append(
                            GroupItem(
                                group_name="General Updates",
                                explanation="Unassigned project modifications",
                                confidence=0.75,
                                file_list=unassigned,
                            )
                        )

                if valid_groups:
                    return ChangeGroupingResult(groups=valid_groups)

        # Fallback heuristic
        logger.info("Using heuristic change grouping fallback.")
        return ChangeGroupingResult(groups=self.heuristic_grouping(file_paths))

