"""Tests for the single_call agent (app/agents/single_call.py) -- the
default reasoning path as of the debate-vs-single-model resolution. Focus:
the citation-integrity enforcement (cited_pmids validated against real
retrieved PMIDs, corrective retry, then hard failure), since that's the
custom logic in this module rather than something already covered by
synthesizer's tests."""

from unittest.mock import MagicMock, patch
from uuid import UUID

import pytest

from app.agents.single_call import single_call

TEST_DEBATE_ID = UUID("12345678-1234-5678-1234-567812345678")


def _mock_conn():
    """A MagicMock psycopg.Connection whose cursor() context manager
    returns incrementing fake ids for each INSERT ... RETURNING id call,
    matching how single_call reads back provenance row ids for retrieved
    papers."""
    conn = MagicMock()
    cursor = MagicMock()
    conn.cursor.return_value.__enter__.return_value = cursor
    ids = iter(range(100, 200))
    cursor.fetchone.side_effect = lambda: (next(ids),)
    return conn, cursor


@pytest.mark.asyncio
async def test_single_call_maps_cited_pmids_to_provenance_ids(mock_env):
    conn, cursor = _mock_conn()

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.call_tool",
        return_value={
            "conclusion": "test conclusion",
            "verdict": "supported",
            "confidence": 0.8,
            "confidence_rationale": "Anchor D applies.",
            "cited_pmids": ["38765432"],  # a real PMID from the brca1 mock set
            "signal_breakdown": {
                "literature": 0.8,
                "protein_evidence": 0.6,
                "clinical_evidence": 0.0,
                "llm_rating": 0.7,
            },
        },
    ):
        result = await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)

    assert result["conclusion"] == "test conclusion"
    assert result["verdict"] == "supported"
    assert result["confidence"] == 0.8
    # Exactly one driving_provenance_id, mapped from the cited PMID to the id
    # this call's own INSERT ... RETURNING id assigned it, not an arbitrary
    # or hallucinated row.
    assert len(result["driving_provenance_ids"]) == 1
    assert isinstance(result["driving_provenance_ids"][0], int)


@pytest.mark.asyncio
async def test_single_call_retries_once_on_bad_pmid_then_succeeds(mock_env):
    conn, cursor = _mock_conn()
    responses = iter([
        {  # first attempt cites a PMID not in this call's retrieval
            "conclusion": "bad",
            "verdict": "supported",
            "confidence": 0.9,
            "confidence_rationale": "x",
            "cited_pmids": ["00000000"],
            "signal_breakdown": {
                "literature": 0.8,
                "protein_evidence": 0.6,
                "clinical_evidence": 0.0,
                "llm_rating": 0.7,
            },
        },
        {  # corrective retry cites a real one
            "conclusion": "corrected",
            "verdict": "supported",
            "confidence": 0.8,
            "confidence_rationale": "Anchor D applies.",
            "cited_pmids": ["38765432"],
            "signal_breakdown": {
                "literature": 0.8,
                "protein_evidence": 0.6,
                "clinical_evidence": 0.0,
                "llm_rating": 0.7,
            },
        },
    ])

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.call_tool", side_effect=lambda *a, **k: next(responses)
    ):
        result = await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)

    assert result["conclusion"] == "corrected"


@pytest.mark.asyncio
async def test_single_call_raises_if_bad_pmid_persists_after_retry(mock_env):
    conn, cursor = _mock_conn()

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.call_tool",
        return_value={
            "conclusion": "bad",
            "verdict": "supported",
            "confidence": 0.9,
            "confidence_rationale": "x",
            "cited_pmids": ["00000000"],  # never a real PMID, on every attempt
            "signal_breakdown": {
                "literature": 0.8,
                "protein_evidence": 0.6,
                "clinical_evidence": 0.0,
                "llm_rating": 0.7,
            },
        },
    ):
        with pytest.raises(RuntimeError, match="cited PMIDs"):
            await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)


@pytest.mark.asyncio
async def test_single_call_returns_signal_breakdown(mock_env):
    conn, cursor = _mock_conn()

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.call_tool",
        return_value={
            "conclusion": "test conclusion",
            "verdict": "supported",
            "confidence": 0.8,
            "confidence_rationale": "Anchor D applies.",
            "cited_pmids": ["38765432"],
            "signal_breakdown": {
                "literature": 0.8,
                "protein_evidence": 0.6,
                "clinical_evidence": 0.0,
                "llm_rating": 0.7,
            },
        },
    ):
        result = await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)

    assert result["signal_breakdown"] == {
        "literature": 0.8,
        "protein_evidence": 0.6,
        "clinical_evidence": 0.0,
        "llm_rating": 0.7,
    }


@pytest.mark.asyncio
async def test_single_call_retries_once_on_invalid_breakdown_then_succeeds(mock_env):
    conn, cursor = _mock_conn()
    responses = iter([
        {  # first attempt: out-of-range signal
            "conclusion": "bad",
            "verdict": "supported",
            "confidence": 0.9,
            "confidence_rationale": "x",
            "cited_pmids": ["38765432"],
            "signal_breakdown": {
                "literature": 1.4,
                "protein_evidence": 0.6,
                "clinical_evidence": 0.0,
                "llm_rating": 0.7,
            },
        },
        {  # corrective retry: valid
            "conclusion": "corrected",
            "verdict": "supported",
            "confidence": 0.8,
            "confidence_rationale": "Anchor D applies.",
            "cited_pmids": ["38765432"],
            "signal_breakdown": {
                "literature": 0.8,
                "protein_evidence": 0.6,
                "clinical_evidence": 0.0,
                "llm_rating": 0.7,
            },
        },
    ])

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.call_tool", side_effect=lambda *a, **k: next(responses)
    ):
        result = await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)

    assert result["conclusion"] == "corrected"
    assert result["signal_breakdown"]["literature"] == 0.8


@pytest.mark.asyncio
async def test_single_call_raises_if_breakdown_invalid_after_retry(mock_env):
    conn, cursor = _mock_conn()

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.call_tool",
        return_value={
            "conclusion": "bad",
            "verdict": "supported",
            "confidence": 0.9,
            "confidence_rationale": "x",
            "cited_pmids": ["38765432"],
            # missing signal_breakdown entirely, on every attempt
        },
    ):
        with pytest.raises(RuntimeError, match="signal_breakdown"):
            await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)
