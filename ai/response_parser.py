"""
Response parser for validating and sanitizing structured LLM outputs.
Treats all model responses as untrusted data.
"""

import json
import re
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field, ValidationError

from utils.logger import logger


class FileChangeItem(BaseModel):
    file_path: str
    change_type: str = "MODIFIED"
    additions: int = 0
    deletions: int = 0
    purpose: str = ""
    is_meaningful: bool = True


class DiffAnalysisResult(BaseModel):
    summary: str = "Code changes detected"
    files: List[FileChangeItem] = Field(default_factory=list)
    total_additions: int = 0
    total_deletions: int = 0


class CodeUnderstandingResult(BaseModel):
    change_summary: str = "Updated repository files"
    primary_language: str = "unknown"
    logical_task: str = "Maintenance"
    risk_level: str = "low"  # low, medium, high
    is_breaking: bool = False
    requires_validation: bool = True
    file_purposes: Dict[str, str] = Field(default_factory=dict)


class GroupItem(BaseModel):
    group_name: str
    explanation: str = ""
    confidence: float = 1.0
    file_list: List[str] = Field(default_factory=list)


class ChangeGroupingResult(BaseModel):
    groups: List[GroupItem] = Field(default_factory=list)


class CommitMessageResult(BaseModel):
    commit_type: str = "chore"
    scope: Optional[str] = None
    subject: str = "update codebase"
    body: Optional[str] = None
    full_message: str = "chore: update codebase"


def extract_json_from_text(text: str) -> Optional[Dict[str, Any]]:
    """
    Safely extract JSON object from text, handling markdown code fences if present.
    """
    if not text or not text.strip():
        return None

    cleaned = text.strip()

    # Try direct parse
    try:
        return json.loads(cleaned)
    except Exception:
        pass

    # Match ```json ... ``` or ``` ... ```
    fence_pattern = re.compile(r"```(?:json)?\s*([\s\S]*?)\s*```", re.IGNORECASE)
    match = fence_pattern.search(cleaned)
    if match:
        try:
            return json.loads(match.group(1).strip())
        except Exception:
            pass

    # Find first { and last }
    first_brace = cleaned.find("{")
    last_brace = cleaned.rfind("}")
    if first_brace != -1 and last_brace != -1 and last_brace > first_brace:
        try:
            return json.loads(cleaned[first_brace : last_brace + 1])
        except Exception:
            pass

    logger.warning("Failed to extract valid JSON from LLM response.")
    return None

