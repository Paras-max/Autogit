"""
Tests for Diff Analysis Agent (agents/diff_analysis_agent.py).
"""

from pathlib import Path
import git
import pytest

from agents.diff_analysis_agent import DiffAnalysisAgent
from ai.llm_client import FallbackClient


@pytest.mark.asyncio
async def test_diff_analysis_modified_files(temp_git_repo: Path):
    readme = temp_git_repo / "README.md"
    readme.write_text("# Updated Readme\nAdded line 1\nAdded line 2\n", encoding="utf-8")

    agent = DiffAnalysisAgent(llm_client=FallbackClient())
    res = await agent.analyze_diff(temp_git_repo)

    assert len(res.files) >= 1
    readme_item = next(f for f in res.files if f.file_path == "README.md")
    assert readme_item.change_type == "MODIFIED"
    assert readme_item.additions >= 2
    assert readme_item.is_meaningful is True
    assert res.total_additions >= 2


@pytest.mark.asyncio
async def test_diff_analysis_new_and_deleted_files(temp_git_repo: Path):
    # Create new file
    new_f = temp_git_repo / "new_module.py"
    new_f.write_text("def hello(): return 'world'\n", encoding="utf-8")

    # Delete README.md
    readme = temp_git_repo / "README.md"
    readme.unlink()

    agent = DiffAnalysisAgent(llm_client=FallbackClient())
    res = await agent.analyze_diff(temp_git_repo)

    paths = [f.file_path for f in res.files]
    assert "new_module.py" in paths
    assert "README.md" in paths

    new_item = next(f for f in res.files if f.file_path == "new_module.py")
    assert new_item.change_type == "CREATED"

    del_item = next(f for f in res.files if f.file_path == "README.md")
    assert del_item.change_type == "DELETED"


@pytest.mark.asyncio
async def test_diff_analysis_binary_file_exclusion(temp_git_repo: Path):
    # Create a dummy image/binary file
    bin_file = temp_git_repo / "image.png"
    bin_file.write_bytes(b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR")

    agent = DiffAnalysisAgent(llm_client=FallbackClient())
    assert agent.is_binary_or_ignored("image.png") is True
    assert agent.is_binary_or_ignored(".git/config") is True
    assert agent.is_binary_or_ignored("node_modules/pkg/index.js") is True
    assert agent.is_binary_or_ignored("src/app.py") is False

    res = await agent.analyze_diff(temp_git_repo)
    paths = [f.file_path for f in res.files]
    assert "image.png" not in paths


@pytest.mark.asyncio
async def test_diff_analysis_large_diff_chunking(temp_git_repo: Path):
    large_file = temp_git_repo / "large.txt"
    # Write 15,000 characters
    large_file.write_text("line of content\n" * 1000, encoding="utf-8")

    agent = DiffAnalysisAgent(llm_client=FallbackClient())
    res = await agent.analyze_diff(temp_git_repo)

    assert len(res.files) == 1
    assert res.files[0].additions >= 1000

