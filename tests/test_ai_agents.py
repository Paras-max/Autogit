"""
Tests for AI Agents and Response Parsers (ai/, agents/).
"""

from unittest.mock import AsyncMock
import pytest

from agents.change_grouping_agent import ChangeGroupingAgent
from agents.code_understanding_agent import CodeUnderstandingAgent
from agents.commit_message_agent import CommitMessageAgent
from ai.llm_client import FallbackClient
from ai.response_parser import (
    CodeUnderstandingResult,
    DiffAnalysisResult,
    FileChangeItem,
    extract_json_from_text,
)


def test_extract_json_from_text_variants():
    # 1. Plain valid JSON
    assert extract_json_from_text('{"key": "val"}') == {"key": "val"}

    # 2. Markdown fenced code block
    fenced = "Here is the response:\n```json\n{\n  \"status\": \"ok\"\n}\n```\nHope that helps!"
    assert extract_json_from_text(fenced) == {"status": "ok"}

    # 3. Text with embedded JSON without fence
    embedded = "Analysis complete: {\"additions\": 5, \"deletions\": 2} done."
    assert extract_json_from_text(embedded) == {"additions": 5, "deletions": 2}

    # 4. Malformed/invalid text
    assert extract_json_from_text("no json here at all") is None
    assert extract_json_from_text("") is None


@pytest.mark.asyncio
async def test_code_understanding_agent_language_and_risk():
    agent = CodeUnderstandingAgent(llm_client=FallbackClient())

    diff_res = DiffAnalysisResult(
        summary="Updated auth models and endpoints",
        files=[
            FileChangeItem(file_path="src/auth.py", change_type="MODIFIED", additions=20, deletions=5),
            FileChangeItem(file_path="src/models.py", change_type="MODIFIED", additions=10, deletions=2),
        ],
        total_additions=30,
        total_deletions=7,
    )

    res = await agent.understand_changes(diff_res)
    assert res.primary_language == "python"
    assert res.risk_level in ("low", "medium", "high")
    assert res.requires_validation is True


@pytest.mark.asyncio
async def test_change_grouping_agent_separates_domains():
    agent = ChangeGroupingAgent(llm_client=FallbackClient())

    diff_res = DiffAnalysisResult(
        summary="Updated code, tests and docs",
        files=[
            FileChangeItem(file_path="src/main.py", change_type="MODIFIED"),
            FileChangeItem(file_path="tests/test_main.py", change_type="MODIFIED"),
            FileChangeItem(file_path="docs/guide.md", change_type="MODIFIED"),
        ],
    )
    understanding = CodeUnderstandingResult(logical_task="Feature enhancement")

    res = await agent.group_changes(diff_res, understanding)
    assert len(res.groups) >= 2  # Separates code/tests from docs
    group_names = [g.group_name.lower() for g in res.groups]
    assert any("documentation" in name for name in group_names)


@pytest.mark.asyncio
async def test_commit_message_agent_conventional_commits():
    agent = CommitMessageAgent(llm_client=FallbackClient())

    diff_res = DiffAnalysisResult(summary="Added user login endpoint")
    understanding = CodeUnderstandingResult(logical_task="Authentication")

    # 1. Fallback Conventional Commit
    res = await agent.generate_commit_message(
        files=["src/auth.py"],
        diff_result=diff_res,
        understanding=understanding,
    )
    assert res.commit_type in ["feat", "fix", "docs", "test", "refactor", "chore"]
    assert len(res.subject) <= 72
    assert "auth" in res.full_message.lower()

    # 2. Mocked LLM response
    mock_llm = AsyncMock()
    mock_llm.generate_response.return_value = (
        '{"commit_type": "feat", "scope": "api", "subject": "add JWT authentication", "body": "Resolves issue #42"}'
    )
    agent_mocked = CommitMessageAgent(llm_client=mock_llm)
    res_mocked = await agent_mocked.generate_commit_message(
        files=["src/auth.py"],
        diff_result=diff_res,
        understanding=understanding,
    )
    assert res_mocked.commit_type == "feat"
    assert res_mocked.scope == "api"
    assert res_mocked.subject == "add JWT authentication"
    assert res_mocked.full_message.startswith("feat(api): add JWT authentication")
    assert "Resolves issue #42" in res_mocked.full_message

