"""Phase 11: per-run resource budget (guardrail G5)."""
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import uuid4

import pytest

from app import budget as budget_mod
from app.budget import Budget, BudgetExceeded, budget_scope, current_budget
from app.llm import _record_usage, call_tool


def test_no_scope_means_no_limit():
    assert current_budget() is None
    budget_mod.begin_call()  # no-ops
    call_tool(None, "m", tool_name="resolve_claim", tool_schema={}, prompt="p")


def test_call_cap_stops_the_run():
    with budget_scope(Budget(max_calls=2)):
        call_tool(None, "m", tool_name="resolve_claim", tool_schema={}, prompt="p")
        call_tool(None, "m", tool_name="resolve_claim", tool_schema={}, prompt="p")
        with pytest.raises(BudgetExceeded) as e:
            call_tool(None, "m", tool_name="resolve_claim", tool_schema={}, prompt="p")
    assert e.value.resource == "calls"


def test_refused_call_is_not_sent_to_the_provider():
    client = MagicMock()
    with budget_scope(Budget(max_calls=0)):
        with pytest.raises(BudgetExceeded):
            call_tool(client, "m", tool_name="t", tool_schema={}, prompt="p")
    client.messages.create.assert_not_called()


def test_usage_is_charged_to_tokens_and_dollars():
    b = Budget()
    with budget_scope(b):
        _record_usage("claude-sonnet-4-5", 1000, 1000)  # $3/M in + $15/M out
    assert b.tokens == 2000 and b.usd == pytest.approx(0.018)


def test_token_cap_and_dollar_cap():
    with budget_scope(Budget(max_tokens=1500)) as b:
        _record_usage("claude-sonnet-4-5", 1000, 1000)
        with pytest.raises(BudgetExceeded) as e:
            b.begin_call()
    assert e.value.resource == "tokens"
    with budget_scope(Budget(max_usd=0.01)) as b:
        _record_usage("claude-sonnet-4-5", 1000, 1000)
        with pytest.raises(BudgetExceeded) as e:
            b.begin_call()
    assert e.value.resource == "usd"


def test_time_cap(monkeypatch):
    now = [100.0]
    monkeypatch.setattr(budget_mod.time, "monotonic", lambda: now[0])
    b = Budget(max_seconds=30)
    b.started = 100.0  # started was stamped with the real clock at construction
    b.begin_call()
    now[0] = 131.0
    with pytest.raises(BudgetExceeded) as e:
        b.begin_call()
    assert e.value.resource == "seconds"


def test_scope_is_removed_afterwards_and_does_not_leak_between_runs():
    with budget_scope(Budget(max_calls=1)):
        pass
    assert current_budget() is None
    with budget_scope(Budget(max_calls=1)) as first:
        first.begin_call()
    with budget_scope(Budget(max_calls=1)) as second:
        second.begin_call()  # a fresh budget, not the exhausted one


@pytest.mark.asyncio
async def test_concurrent_tasks_share_one_pool():
    async def one():
        call_tool(None, "m", tool_name="resolve_claim", tool_schema={}, prompt="p")

    with budget_scope(Budget(max_calls=3)) as b:
        results = await asyncio.gather(*(one() for _ in range(5)), return_exceptions=True)
    assert sum(isinstance(r, BudgetExceeded) for r in results) == 2 and b.calls == 3


def test_from_env(monkeypatch):
    monkeypatch.setenv("BUDGET_MAX_CALLS", "5")
    monkeypatch.setenv("BUDGET_MAX_USD", "0.25")
    b = Budget.from_env()
    assert (b.max_calls, b.max_usd) == (5, 0.25)


# --- wiring into the API --------------------------------------------------------

@pytest.mark.asyncio
async def test_both_pipelines_run_inside_a_fresh_budget_each_time():
    from app import main

    seen = []

    async def fake_single_call(conn, claim, debate_id):
        seen.append(current_budget())
        return {"conclusion": "c", "verdict": "unresolved", "confidence": 0.5, "confidence_rationale": "x",
                "signal_breakdown": {"literature": 0, "protein_evidence": 0, "clinical_evidence": 0, "llm_rating": 0},
                "driving_provenance_ids": [], "papers": [], "trials": [], "retrieval_warnings": []}

    conn = MagicMock()
    conn.cursor.return_value.__enter__.return_value.fetchall.return_value = []
    with patch.object(main, "connect", return_value=conn), patch.object(main, "single_call", fake_single_call):
        await main.run_synthesis_pipeline("claim", str(uuid4()))
        await main.run_synthesis_pipeline("claim", str(uuid4()))
    assert all(b is not None for b in seen) and seen[0] is not seen[1]
    assert current_budget() is None


def test_budget_exceeded_is_a_429_not_a_500(client):
    from app import main

    with patch.object(main, "run_synthesis_pipeline", AsyncMock(side_effect=BudgetExceeded("usd", 2.1, 2.0))):
        r = client.post("/debate", json={"claim": "Glucosamine reduces pain in osteoarthritis"})
    assert r.status_code == 429 and r.json()["resource"] == "usd"
