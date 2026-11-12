"""
Task Planning Agent for AutoGit AI (Phase 3).
Formulates a development plan selecting 2-3 safe, targeted, high-value modifications.
"""

from dataclasses import dataclass, field
import asyncio
import json
from typing import Any, Dict, List, Optional

from ai.llm_client import BaseLLMClient
from ai.provider_factory import AIProviderFactory
from ai.response_parser import extract_json_from_text
from database.models import DevelopmentTaskModel, ProjectContextModel
from utils.logger import logger


@dataclass
class PlannedChange:
    task_id: int
    target_file: str
    action_type: str  # 'create', 'modify'
    description: str


@dataclass
class SessionPlan:
    repository_id: int
    planned_changes: List[PlannedChange] = field(default_factory=list)
    reasoning: str = ""
    selected_task_ids: List[int] = field(default_factory=list)


class TaskPlanningAgent:
    """
    Plans 2-3 concrete code modifications for an autonomous development session.
    """

    def __init__(self, llm_client: Optional[BaseLLMClient] = None):
        self.llm_client = llm_client or AIProviderFactory.get_client()

    def plan_session(
        self,
        repository_id: int,
        context: Optional[ProjectContextModel],
        tasks: List[DevelopmentTaskModel],
        max_changes: int = 3,
    ) -> SessionPlan:
        """
        Formulate a development session plan with approximately 2-3 changes.
        """
        if not tasks:
            return SessionPlan(
                repository_id=repository_id,
                reasoning="No suitable pending tasks available for this session.",
            )

        # Select top 2-3 tasks based on priority
        selected_tasks = tasks[:max_changes]

        prompt = self._build_prompt(context, selected_tasks)
        try:
            raw_response = asyncio.run(
                self.llm_client.generate_response(
                    system_prompt="You are a software architect designing a development session plan.",
                    user_prompt=prompt,
                )
            )
        except Exception as e:
            logger.debug(f"LLM call failed in task planner: {e}")
            raw_response = None

        parsed = extract_json_from_text(raw_response) if raw_response else None

        if parsed and isinstance(parsed, dict) and "planned_changes" in parsed:
            changes: List[PlannedChange] = []
            for item in parsed["planned_changes"][:max_changes]:
                changes.append(
                    PlannedChange(
                        task_id=int(item.get("task_id", selected_tasks[0].id)),
                        target_file=item.get("target_file", "utils/helpers.py"),
                        action_type=item.get("action_type", "modify"),
                        description=item.get("description", "Code modification"),
                    )
                )
            return SessionPlan(
                repository_id=repository_id,
                planned_changes=changes,
                reasoning=parsed.get("reasoning", "AI generated session plan"),
                selected_task_ids=[t.id for t in selected_tasks if t.id],
            )

        # Fallback heuristic plan
        return self._heuristic_plan(repository_id, context, selected_tasks)

    def _build_prompt(
        self, context: Optional[ProjectContextModel], tasks: List[DevelopmentTaskModel]
    ) -> str:
        lang = context.primary_language if context else "python"
        framework = context.framework if context else "None"
        tasks_text = "\n".join(
            [f"- ID: {t.id}, Title: {t.title}, Type: {t.task_type}, Priority: {t.priority}" for t in tasks]
        )

        return f"""You are a Senior Software Architect planning an autonomous development session.
Project Language: {lang}
Framework: {framework}

Available Tasks:
{tasks_text}

Plan approximately 2 to 3 safe, targeted, high-value code modifications.
Never touch secrets, .env files, private keys, or infrastructure outside the project.

Respond ONLY with valid JSON in this schema:
{{
  "reasoning": "Brief explanation of the selected plan",
  "planned_changes": [
    {{
      "task_id": <int>,
      "target_file": "relative/path/to/file.py",
      "action_type": "create" or "modify",
      "description": "Specific code modification to perform"
    }}
  ]
}}
"""

    def _heuristic_plan(
        self,
        repository_id: int,
        context: Optional[ProjectContextModel],
        tasks: List[DevelopmentTaskModel],
    ) -> SessionPlan:
        """Deterministic heuristic plan when LLM is unavailable."""
        changes: List[PlannedChange] = []
        lang = (context.primary_language if context else "python").lower()

        for idx, task in enumerate(tasks):
            t_type = task.task_type.lower()
            if t_type == "test":
                target = f"tests/test_autonomous_{idx+1}.py" if lang == "python" else f"tests/autonomous_{idx+1}.test.js"
                act = "create"
            elif t_type == "documentation":
                target = "docs/overview.md"
                act = "modify"
            elif t_type == "refactor":
                target = "utils/helpers.py" if lang == "python" else "src/utils.js"
                act = "modify"
            else:
                target = f"core/feature_{idx+1}.py" if lang == "python" else f"src/feature_{idx+1}.js"
                act = "create"

            changes.append(
                PlannedChange(
                    task_id=task.id or (idx + 1),
                    target_file=target,
                    action_type=act,
                    description=f"Implement '{task.title}': {task.description or 'Planned improvement'}",
                )
            )

        return SessionPlan(
            repository_id=repository_id,
            planned_changes=changes,
            reasoning="Heuristic session plan generated from backlog priority.",
            selected_task_ids=[t.id for t in tasks if t.id],
        )

