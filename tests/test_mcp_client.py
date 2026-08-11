"""Guards search_pubmed's mock-fallback behavior: misconfiguration must be a
hard failure, not a silent fallback to mock data (see mcp_client.py's
docstring for why -- a debate run advertised as grounded in real literature
must not be able to silently become a mock run)."""

import pytest

from app.mcp_client import search_pubmed


@pytest.mark.asyncio
async def test_raises_when_biolab_project_path_unset(monkeypatch):
    monkeypatch.delenv("MOCK_RETRIEVAL", raising=False)
    monkeypatch.delenv("BIOLAB_PROJECT_PATH", raising=False)

    with pytest.raises(RuntimeError, match="BIOLAB_PROJECT_PATH"):
        await search_pubmed("brca1", agent_id="test-agent")


@pytest.mark.asyncio
async def test_raises_when_biolab_db_path_unset(monkeypatch):
    monkeypatch.delenv("MOCK_RETRIEVAL", raising=False)
    monkeypatch.setenv("BIOLAB_PROJECT_PATH", "/some/path")
    monkeypatch.delenv("BIOLAB_DB_PATH", raising=False)

    with pytest.raises(RuntimeError, match="BIOLAB_DB_PATH"):
        await search_pubmed("brca1", agent_id="test-agent")


@pytest.mark.asyncio
async def test_explicit_mock_mode_still_works(monkeypatch):
    monkeypatch.setenv("MOCK_RETRIEVAL", "true")
    monkeypatch.delenv("BIOLAB_PROJECT_PATH", raising=False)
    monkeypatch.delenv("BIOLAB_DB_PATH", raising=False)

    result = await search_pubmed("brca1", agent_id="test-agent", max_results=2)

    assert result["query_echo"] == "brca1"
    assert len(result["papers"]) == 2
