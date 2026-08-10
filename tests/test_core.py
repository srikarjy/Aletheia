"""Tests for core utilities: embeddings, database, MCP client."""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import json


class TestEmbeddings:
    """Tests for embeddings module."""

    def test_embed_returns_vector(self, mock_env):
        """embed() returns a vector of correct dimension."""
        # Patch the module's _client directly after import
        with patch("app.embeddings._client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_client.embeddings.create.return_value = mock_response
            
            from app.embeddings import embed
            vector = embed("Test text")
            
            assert isinstance(vector, list)
            assert len(vector) == 1536
            assert all(isinstance(x, float) for x in vector)

    def test_embed_calls_openai_with_correct_model(self, mock_env):
        """embed() calls OpenAI with text-embedding-3-small."""
        with patch("app.embeddings._client") as mock_client:
            mock_response = MagicMock()
            mock_response.data = [MagicMock(embedding=[0.1] * 1536)]
            mock_client.embeddings.create.return_value = mock_response
            
            from app.embeddings import embed
            embed("Test text")
            
            mock_client.embeddings.create.assert_called_once()
            call_args = mock_client.embeddings.create.call_args
            assert call_args.kwargs["model"] == "text-embedding-3-small"


class TestCallToolTruncation:
    """Tests for app.llm.call_tool's max_tokens truncation handling — the Phase 3 bug
    where a truncated tool_use response isn't an API error, just stop_reason=="max_tokens"
    with partial JSON."""

    def _response(self, stop_reason: str, tool_input: dict | None = None) -> MagicMock:
        resp = MagicMock()
        resp.stop_reason = stop_reason
        block = MagicMock()
        block.type = "tool_use"
        block.input = tool_input or {}
        resp.content = [block]
        return resp

    def test_retries_with_increased_max_tokens_then_succeeds(self, mock_env):
        """A max_tokens stop_reason triggers a retry at a higher max_tokens, not an
        immediate raise, and the successful retry's result is returned."""
        from app.llm import call_tool

        client = MagicMock()
        client.messages.create.side_effect = [
            self._response("max_tokens"),
            self._response("end_turn", {"answer": "ok"}),
        ]

        result = call_tool(
            client, "claude-sonnet-4-5",
            tool_name="submit_baseline", tool_schema={"type": "object"}, prompt="x",
        )

        assert result == {"answer": "ok"}
        assert client.messages.create.call_count == 2
        first_max_tokens = client.messages.create.call_args_list[0].kwargs["max_tokens"]
        second_max_tokens = client.messages.create.call_args_list[1].kwargs["max_tokens"]
        assert second_max_tokens > first_max_tokens

    def test_gives_up_after_hitting_token_limit(self, mock_env):
        """If every retry keeps truncating, call_tool eventually raises instead of
        retrying forever or returning partial/invalid JSON."""
        from app.llm import call_tool, MAX_TOKENS_LIMIT

        client = MagicMock()
        client.messages.create.return_value = self._response("max_tokens")

        with pytest.raises(RuntimeError, match="still truncated"):
            call_tool(
                client, "claude-sonnet-4-5",
                tool_name="submit_baseline", tool_schema={"type": "object"}, prompt="x",
            )

        # Bounded: must not have looped indefinitely.
        assert client.messages.create.call_count < 100
        last_max_tokens = client.messages.create.call_args_list[-1].kwargs["max_tokens"]
        assert last_max_tokens <= MAX_TOKENS_LIMIT

    def test_retry_disabled_raises_immediately_on_first_truncation(self, mock_env):
        """retry_on_truncation=False preserves the original fail-fast behavior."""
        from app.llm import call_tool

        client = MagicMock()
        client.messages.create.return_value = self._response("max_tokens")

        with pytest.raises(RuntimeError, match="truncated"):
            call_tool(
                client, "claude-sonnet-4-5",
                tool_name="submit_baseline", tool_schema={"type": "object"}, prompt="x",
                retry_on_truncation=False,
            )

        assert client.messages.create.call_count == 1

    def test_legacy_tool_and_prompt_signature_still_works(self, mock_env):
        """The pre-refactor (tool, prompt) positional call signature is still honored,
        since it's the public contract other code may still rely on."""
        from app.llm import call_tool

        client = MagicMock()
        client.messages.create.return_value = self._response("end_turn", {"answer": "ok"})

        result = call_tool(
            client, "claude-sonnet-4-5", 2048,
            {"name": "submit_baseline", "input_schema": {"type": "object"}}, "x",
        )

        assert result == {"answer": "ok"}

    def test_zero_retry_increment_does_not_loop_forever(self, mock_env, monkeypatch):
        """A misconfigured CLAUDE_MAX_TOKENS_RETRY_INCREMENT=0 must not make _max_tokens
        stall below the ceiling forever — the attempt count is a backstop independent of
        the increment."""
        import app.llm as llm_module
        monkeypatch.setattr(llm_module, "MAX_TOKENS_RETRY_INCREMENT", 0)

        client = MagicMock()
        client.messages.create.return_value = self._response("max_tokens")

        with pytest.raises(RuntimeError, match="still truncated"):
            llm_module.call_tool(
                client, "claude-sonnet-4-5",
                tool_name="submit_baseline", tool_schema={"type": "object"}, prompt="x",
            )

        assert client.messages.create.call_count < 100


class TestCostTracker:
    """Tests for app.llm's usage/cost tracking."""

    def _response(self, input_tokens: int, output_tokens: int, tool_input: dict) -> MagicMock:
        resp = MagicMock()
        resp.stop_reason = "end_turn"
        resp.usage.input_tokens = input_tokens
        resp.usage.output_tokens = output_tokens
        block = MagicMock()
        block.type = "tool_use"
        block.input = tool_input
        resp.content = [block]
        return resp

    def test_call_tool_records_usage_and_computes_cost(self, mock_env):
        from app.llm import call_tool, reset_cost_tracker

        reset_cost_tracker()
        client = MagicMock()
        client.messages.create.return_value = self._response(1_000_000, 1_000_000, {"ok": True})

        call_tool(
            client, "claude-sonnet-4-5",
            tool_name="t", tool_schema={"type": "object"}, prompt="x",
        )

        summary = reset_cost_tracker()
        assert summary["input_tokens"] == 1_000_000
        assert summary["output_tokens"] == 1_000_000
        assert summary["calls"] == 1
        # $3/1M input + $15/1M output at claim-set pricing for claude-sonnet-4-5
        assert summary["cost_usd"] == pytest.approx(18.00)

    def test_unpriced_model_tracks_tokens_but_zero_cost(self, mock_env):
        """A model missing from PRICING_PER_MILLION_TOKENS shouldn't crash or silently
        fabricate a cost — tokens are still counted, cost is explicitly zero."""
        from app.llm import call_tool, reset_cost_tracker

        reset_cost_tracker()
        client = MagicMock()
        client.messages.create.return_value = self._response(100, 50, {"ok": True})

        call_tool(
            client, "some-future-model-not-in-pricing-table",
            tool_name="t", tool_schema={"type": "object"}, prompt="x",
        )

        summary = reset_cost_tracker()
        assert summary["input_tokens"] == 100
        assert summary["cost_usd"] == 0.0

    def test_reset_returns_snapshot_and_zeroes_tracker(self, mock_env):
        from app.llm import call_tool, get_cost_summary, reset_cost_tracker

        reset_cost_tracker()
        client = MagicMock()
        client.messages.create.return_value = self._response(10, 10, {"ok": True})
        call_tool(client, "claude-sonnet-4-5", tool_name="t", tool_schema={"type": "object"}, prompt="x")

        snapshot = reset_cost_tracker()
        assert snapshot["calls"] == 1
        assert get_cost_summary() == {"input_tokens": 0, "output_tokens": 0, "cost_usd": 0.0, "calls": 0}


class TestDatabase:
    """Tests for database module."""

    @pytest.mark.asyncio
    async def test_get_pool_returns_pool(self, mock_env):
        """get_pool returns a connection pool - skipped if asyncpg not available."""
        pytest.skip("asyncpg not available in test environment")

    @pytest.mark.asyncio
    async def test_init_db_creates_tables(self, mock_env):
        """init_db creates required tables - skipped if asyncpg not available."""
        pytest.skip("asyncpg not available in test environment")


class TestMCPClient:
    """Tests for MCP client."""

    @pytest.mark.asyncio
    async def test_search_pubmed_mock_mode(self, mock_env):
        """search_pubmed returns mock data when MOCK_RETRIEVAL=true."""
        from app.mcp_client import search_pubmed
        
        result = await search_pubmed("BRCA1 cancer", "test:agent", 3)
        
        assert "query_echo" in result
        assert "papers" in result
        assert len(result["papers"]) == 3
        for paper in result["papers"]:
            assert "pmid" in paper
            assert "retrieval_id" in paper
            assert "title" in paper
            assert "abstract" in paper

    @pytest.mark.asyncio
    async def test_search_pubmed_mock_filters_by_query(self, mock_env):
        """Mock retrieval returns relevant papers based on query keywords."""
        from app.mcp_client import search_pubmed
        
        result = await search_pubmed("BRCA1 pancreatic cancer", "test:agent", 5)
        assert len(result["papers"]) == 5
        assert "BRCA1" in result["papers"][0]["title"] or "BRCA1" in result["papers"][0]["abstract"]
        
        result = await search_pubmed("Vitamin D COVID", "test:agent", 5)
        assert len(result["papers"]) == 5
        assert "Vitamin D" in result["papers"][0]["title"] or "Vitamin D" in result["papers"][0]["abstract"]

    @pytest.mark.asyncio
    async def test_search_pubmed_respects_max_results(self, mock_env):
        """search_pubmed respects max_results parameter."""
        from app.mcp_client import search_pubmed
        
        result = await search_pubmed("test", "test:agent", 2)
        assert len(result["papers"]) == 2
        
        result = await search_pubmed("test", "test:agent", 10)
        assert len(result["papers"]) == 5

    @pytest.mark.asyncio
    async def test_search_pubmed_real_mode_requires_biolab_path(self, mock_env):
        """Real mode requires BIOLAB_PROJECT_PATH."""
        with patch.dict("os.environ", {"MOCK_RETRIEVAL": "false", "BIOLAB_PROJECT_PATH": ""}, clear=False):
            from app.mcp_client import search_pubmed
            
            with pytest.warns(UserWarning, match="BIOLAB_PROJECT_PATH not set"):
                result = await search_pubmed("test", "test:agent", 5)
                assert "papers" in result


class TestSchemas:
    """Tests for Pydantic schemas."""

    def test_debate_request_schema(self):
        """DebateRequest validates correctly."""
        from app.schemas import DebateRequest
        from pydantic import ValidationError
        
        req = DebateRequest(claim="Test claim")
        assert req.claim == "Test claim"
        
        with pytest.raises(ValidationError):
            DebateRequest(claim="")
        
        with pytest.raises(ValidationError):
            DebateRequest()

    def test_debate_response_schema(self, sample_debate_result):
        """DebateResponse validates correctly."""
        from app.schemas import DebateResponse
        from uuid import UUID
        
        test_result = sample_debate_result.copy()
        test_result["debate_id"] = UUID("12345678-1234-5678-1234-567812345678")
        
        resp = DebateResponse(**test_result)
        assert resp.verdict == "unresolved"
        assert resp.confidence == 0.5
        assert len(resp.sources) == 2

    def test_transcript_entry_schema(self):
        """TranscriptEntry validates correctly."""
        from app.schemas import TranscriptEntry
        
        entry = TranscriptEntry(
            agent="advocate",
            action="retrieve",
            detail={"title": "Test paper"},
            source_paper_id="123"
        )
        assert entry.agent == "advocate"
        assert entry.action == "retrieve"
        assert entry.source_paper_id == "123"

    def test_source_schema(self):
        """Source validates correctly."""
        from app.schemas import Source
        
        src = Source(
            paper_id="123",
            title="Test paper",
            used_by=["advocate", "skeptic"]
        )
        assert src.paper_id == "123"
        assert len(src.used_by) == 2


class TestMCPClientSchemas:
    """Tests for MCP client related schemas."""

    def test_mcp_search_result(self):
        """MCP search result structure."""
        from app.mcp_client import search_pubmed
        
        import asyncio
        result = asyncio.run(search_pubmed("test", "test:agent", 1))
        
        assert "query_echo" in result
        assert "papers" in result
        assert len(result["papers"]) == 1
        paper = result["papers"][0]
        assert "pmid" in paper
        assert "retrieval_id" in paper
        assert "title" in paper
        assert "abstract" in paper