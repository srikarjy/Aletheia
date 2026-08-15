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


VALID_BREAKDOWN = {
    "literature": 0.8,
    "protein_evidence": 0.0,
    "clinical_evidence": 0.7,
    "llm_rating": 0.7,
}

MOCK_TRIALS = {
    "query_echo": "brca1 pancreatic cancer",
    "studies": [
        {
            "nct_id": "NCT01234567",
            "retrieval_id": "mock_trial_001",
            "title": "PARP inhibition in BRCA1-mutated pancreatic cancer",
            "status": "COMPLETED",
            "phase": "PHASE3",
        }
    ],
}


@pytest.mark.asyncio
async def test_single_call_accepts_nct_citations_and_returns_trials(mock_env):
    conn, cursor = _mock_conn()

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.search_clinicaltrials", return_value=MOCK_TRIALS
    ), patch(
        "app.agents.single_call.call_tool",
        return_value={
            "conclusion": "trial-backed conclusion",
            "verdict": "supported",
            "confidence": 0.8,
            "confidence_rationale": "Anchor D applies.",
            # cites a paper AND a trial record -- the NCT id must validate
            "cited_pmids": ["38765432", "NCT01234567"],
            "signal_breakdown": VALID_BREAKDOWN,
        },
    ):
        result = await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)

    assert result["trials"] == MOCK_TRIALS["studies"]
    assert result["retrieval_warnings"] == []
    # Both the paper and the trial citation map to real provenance row ids
    assert len(result["driving_provenance_ids"]) == 2


@pytest.mark.asyncio
async def test_single_call_rejects_uncited_nct_id(mock_env):
    conn, cursor = _mock_conn()

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.search_clinicaltrials", return_value=MOCK_TRIALS
    ), patch(
        "app.agents.single_call.call_tool",
        return_value={
            "conclusion": "bad",
            "verdict": "supported",
            "confidence": 0.9,
            "confidence_rationale": "x",
            "cited_pmids": ["NCT99999999"],  # not in this call's retrieval
            "signal_breakdown": VALID_BREAKDOWN,
        },
    ):
        with pytest.raises(RuntimeError, match="cited PMIDs"):
            await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)


@pytest.mark.asyncio
async def test_single_call_degrades_with_warning_when_supplementary_source_fails(mock_env):
    conn, cursor = _mock_conn()

    async def failing_epmc(*a, **k):
        raise RuntimeError("Europe PMC is down")

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.search_europepmc", side_effect=failing_epmc
    ), patch(
        "app.agents.single_call.call_tool",
        return_value={
            "conclusion": "still grounded in pubmed",
            "verdict": "supported",
            "confidence": 0.8,
            "confidence_rationale": "Anchor D applies.",
            "cited_pmids": ["38765432"],
            "signal_breakdown": VALID_BREAKDOWN,
        },
    ):
        result = await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)

    assert result["conclusion"] == "still grounded in pubmed"
    assert len(result["retrieval_warnings"]) == 1
    assert "europepmc" in result["retrieval_warnings"][0]


@pytest.mark.asyncio
async def test_single_call_fails_hard_when_pubmed_fails(mock_env):
    conn, cursor = _mock_conn()

    async def failing_pubmed(*a, **k):
        raise RuntimeError("PubMed retrieval failed")

    with patch("app.agents.single_call.embed", return_value=[0.0]), patch(
        "app.agents.single_call.search_pubmed", side_effect=failing_pubmed
    ):
        with pytest.raises(RuntimeError, match="PubMed retrieval failed"):
            await single_call(conn, "brca1 pancreatic cancer", TEST_DEBATE_ID)


def test_trials_query_strips_assertion_language():
    from app.agents.single_call import _trials_query

    assert _trials_query(
        "Vemurafenib improves survival in BRAF V600E metastatic melanoma"
    ) == "Vemurafenib BRAF V600E metastatic melanoma"
    # A degenerate all-stopword claim falls back to the raw text, never empty
    assert _trials_query("improves the outcomes") == "improves the outcomes"
