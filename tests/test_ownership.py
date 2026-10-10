"""Phase 10b: per-user ownership of jobs and research memory (the anti-IDOR layer).

Authentication says who you are; these tests are about what that identity may touch.
Every test is framed as one student trying to reach another student's data.
These run on the in-memory path (no Postgres); tests/test_ownership_postgres.py runs
the same rules against real SQL when TEST_DATABASE_URL is set.
"""
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest
from auth_helpers import mint_test_token
from fastapi.testclient import TestClient

from app.infrastructure.state import ANY_OWNER, RuntimeState
from app.schemas import DebateResponse

ALICE, BOB, ADMIN = "alice@bu.edu", "bob@bu.edu", "root@bu.edu"
CLAIM = "Glucosamine reduces pain in osteoarthritis"


def as_user(sub: str, role: str = "student") -> dict:
    return {"Authorization": f"Bearer {mint_test_token(sub, role)}"}


@pytest.fixture
def api():
    from app.main import app, claim_cache, runtime_state

    def wipe():
        runtime_state.jobs.clear()
        runtime_state.memories.clear()
        runtime_state.responses.clear()
        claim_cache.clear()

    wipe()
    yield TestClient(app)
    wipe()


@pytest.fixture(autouse=True)
def fake_pipeline():
    """Replace the LLM pipeline with a canned DebateResponse so no model is called."""

    async def fake(claim: str, debate_id: str) -> DebateResponse:
        return DebateResponse(
            debate_id=debate_id, claim=claim, conclusion="c", verdict="unresolved",
            confidence=0.5, confidence_rationale="Anchor B.", driving_provenance_ids=[],
            transcript=[], sources=[],
        )

    with patch("app.main.run_synthesis_pipeline", AsyncMock(side_effect=fake)), patch(
        "app.main.run_debate_pipeline", AsyncMock(side_effect=fake)
    ):
        yield


def submit_job(api, who: str, claim: str = CLAIM, role: str = "student") -> dict:
    r = api.post("/debate/async", json={"claim": claim}, headers=as_user(who, role))
    assert r.status_code == 200, r.text
    return r.json()


def run_sync(api, who: str, claim: str = CLAIM, role: str = "student") -> dict:
    r = api.post("/debate", json={"claim": claim}, headers=as_user(who, role))
    assert r.status_code == 200, r.text
    return r.json()


# --- jobs ---------------------------------------------------------------------

def test_owner_can_read_their_own_job(api):
    job = submit_job(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    r = api.get(f"/debate/jobs/{job['job_id']}", headers=as_user(ALICE))
    assert r.status_code == 200 and r.json()["status"] == "completed"


def test_another_student_cannot_read_the_job(api):
    job = submit_job(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    assert api.get(f"/debate/jobs/{job['job_id']}", headers=as_user(BOB)).status_code == 404


def test_someone_elses_job_is_indistinguishable_from_a_missing_one(api):
    """No existence oracle: if Bob could tell 'not yours' from 'does not exist', he
    could still enumerate which job ids are real."""
    job = submit_job(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    theirs = api.get(f"/debate/jobs/{job['job_id']}", headers=as_user(BOB))
    missing = api.get(f"/debate/jobs/{uuid4()}", headers=as_user(BOB))
    assert (theirs.status_code, theirs.json()) == (missing.status_code, missing.json())


def test_job_listing_is_scoped_to_the_caller(api):
    a = submit_job(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    b = submit_job(api, BOB, claim="Low-dose aspirin reduces all-cause mortality in healthy older adults")
    alice_ids = {j["job_id"] for j in api.get("/debate/jobs", headers=as_user(ALICE)).json()["jobs"]}
    bob_ids = {j["job_id"] for j in api.get("/debate/jobs", headers=as_user(BOB)).json()["jobs"]}
    assert alice_ids == {a["job_id"]} and bob_ids == {b["job_id"]}


def test_job_listing_total_does_not_count_other_peoples_jobs(api):
    submit_job(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    submit_job(api, BOB, claim="Low-dose aspirin reduces all-cause mortality in healthy older adults")
    assert api.get("/debate/jobs", headers=as_user(BOB)).json()["total"] == 1


def test_admin_sees_every_job(api):
    a = submit_job(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    b = submit_job(api, BOB, claim="Low-dose aspirin reduces all-cause mortality in healthy older adults")
    ids = {j["job_id"] for j in api.get("/debate/jobs", headers=as_user(ADMIN, "admin")).json()["jobs"]}
    assert {a["job_id"], b["job_id"]} <= ids
    assert api.get(f"/debate/jobs/{a['job_id']}", headers=as_user(ADMIN, "admin")).status_code == 200


def test_another_student_cannot_delete_the_job_and_it_survives(api):
    job = submit_job(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    assert api.delete(f"/debate/jobs/{job['job_id']}", headers=as_user(BOB)).status_code == 404
    assert api.get(f"/debate/jobs/{job['job_id']}", headers=as_user(ALICE)).status_code == 200


def test_owner_and_admin_can_delete(api):
    mine = submit_job(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    theirs = submit_job(api, BOB, claim="Low-dose aspirin reduces all-cause mortality in healthy older adults")
    assert api.delete(f"/debate/jobs/{mine['job_id']}", headers=as_user(ALICE)).status_code == 200
    assert api.delete(f"/debate/jobs/{theirs['job_id']}", headers=as_user(ADMIN, "admin")).status_code == 200


def test_admin_owns_the_jobs_they_submit(api):
    job = submit_job(api, ADMIN, role="admin", claim="Vitamin C supplementation prevents the common cold")
    assert api.get(f"/debate/jobs/{job['job_id']}", headers=as_user(ALICE)).status_code == 404


def test_identity_comes_from_the_token_not_the_request(api):
    """A caller cannot claim to be someone else via query string, body or header."""
    job = submit_job(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    sneaky = api.get(
        f"/debate/jobs/{job['job_id']}?owner={ALICE}&sub={ALICE}",
        headers={**as_user(BOB), "X-User": ALICE, "X-Owner": ALICE},
    )
    assert sneaky.status_code == 404


def test_owner_match_is_exact_not_prefix_or_case_insensitive(api):
    job = submit_job(api, "alice", claim="Vitamin C supplementation prevents the common cold")
    for impostor in ("alice2", "Alice", "alic", "alice ", "ALICE"):
        r = api.get(f"/debate/jobs/{job['job_id']}", headers=as_user(impostor))
        assert r.status_code == 404, f"{impostor!r} reached alice's job"


# --- research memory ----------------------------------------------------------

def test_memory_is_private_to_its_owner(api):
    result = run_sync(api, ALICE)
    mid = result["debate_id"]
    assert api.get(f"/memory/research/{mid}", headers=as_user(ALICE)).status_code == 200
    assert api.get(f"/memory/research/{mid}", headers=as_user(BOB)).status_code == 404
    assert api.get(f"/memory/research/{mid}", headers=as_user(ADMIN, "admin")).status_code == 200


def test_memory_listing_is_scoped(api):
    a = run_sync(api, ALICE, claim="Vitamin C supplementation prevents the common cold")
    b = run_sync(api, BOB, claim="Low-dose aspirin reduces all-cause mortality in healthy older adults")
    alice_ids = {m["debate_id"] for m in api.get("/memory/research", headers=as_user(ALICE)).json()["items"]}
    assert alice_ids == {a["debate_id"]}
    assert b["debate_id"] not in alice_ids


def test_memory_listing_never_exposes_owner_or_full_result(api):
    run_sync(api, ALICE)
    item = api.get("/memory/research", headers=as_user(ALICE)).json()["items"][0]
    assert "owner" not in item and "result" not in item


def test_another_student_cannot_delete_memory_and_it_survives(api):
    mid = run_sync(api, ALICE)["debate_id"]
    assert api.delete(f"/memory/research/{mid}", headers=as_user(BOB)).status_code == 404
    assert api.get(f"/memory/research/{mid}", headers=as_user(ALICE)).status_code == 200


def test_memory_miss_and_forbidden_are_identical(api):
    mid = run_sync(api, ALICE)["debate_id"]
    theirs = api.get(f"/memory/research/{mid}", headers=as_user(BOB))
    missing = api.get(f"/memory/research/{uuid4()}", headers=as_user(BOB))
    assert (theirs.status_code, theirs.json()) == (missing.status_code, missing.json())


def test_shared_response_cache_does_not_share_memory(api):
    """The claim cache is shared (public science, saves money) but each caller's memory
    record is their own: Bob's cache hit must not appear in Alice's history or vice versa."""
    a = run_sync(api, ALICE)
    b = run_sync(api, BOB)  # same claim -> served from cache
    assert a["debate_id"] != b["debate_id"]
    assert {m["debate_id"] for m in api.get("/memory/research", headers=as_user(ALICE)).json()["items"]} == {a["debate_id"]}
    assert {m["debate_id"] for m in api.get("/memory/research", headers=as_user(BOB)).json()["items"]} == {b["debate_id"]}
    assert api.get(f"/memory/research/{a['debate_id']}", headers=as_user(BOB)).status_code == 404


def test_cached_async_submission_is_still_owned_by_the_caller(api):
    run_sync(api, ALICE)  # warms the cache
    cached = submit_job(api, BOB)  # cache-hit path of /debate/async
    assert cached["cache_hit"] is True
    assert {m["debate_id"] for m in api.get("/memory/research", headers=as_user(BOB)).json()["items"]} == {cached["debate_id"]}


# --- legacy rows and storage-API guarantees -----------------------------------

def test_rows_without_an_owner_are_admin_only(api):
    """Data created before ownership existed has no owner. Nobody 'inherits' it."""
    from app.main import runtime_state

    legacy_job = str(uuid4())
    runtime_state.jobs[legacy_job] = {"status": "completed", "claim": CLAIM, "created_at": 1.0}
    legacy_debate = str(uuid4())
    runtime_state.memories[legacy_debate] = {
        "debate_id": legacy_debate, "claim": CLAIM, "verdict": "unresolved", "confidence": 0.5,
        "pipeline": "single_call", "from_cache": False, "created_at": 1.0, "owner": None,
        "result": {
            "debate_id": legacy_debate, "claim": CLAIM, "conclusion": "c", "verdict": "unresolved",
            "confidence": 0.5, "confidence_rationale": "x", "driving_provenance_ids": [],
            "transcript": [], "sources": [],
        },
    }
    assert api.get(f"/debate/jobs/{legacy_job}", headers=as_user(ALICE)).status_code == 404
    assert api.get(f"/memory/research/{legacy_debate}", headers=as_user(ALICE)).status_code == 404
    assert api.get(f"/debate/jobs/{legacy_job}", headers=as_user(ADMIN, "admin")).status_code == 200
    assert api.get(f"/memory/research/{legacy_debate}", headers=as_user(ADMIN, "admin")).status_code == 200


def test_storage_api_refuses_calls_that_forget_the_owner():
    """The structural guarantee: there is no default scope to forget."""
    state = RuntimeState()
    for call in (
        lambda: state.get_job("x"),
        lambda: state.list_jobs(10, 0),
        lambda: state.delete_job("x"),
        lambda: state.get_memory("x"),
        lambda: state.list_memories(10),
        lambda: state.delete_memory("x"),
        lambda: state.remember({"debate_id": "x", "claim": "c", "verdict": "v", "confidence": 0.1}, "p"),
    ):
        with pytest.raises(TypeError):
            call()


def test_remember_rejects_missing_or_wildcard_owner():
    state = RuntimeState()
    payload = {"debate_id": str(uuid4()), "claim": "c", "verdict": "v", "confidence": 0.1}
    for bad in ("", None, ANY_OWNER):
        with pytest.raises(ValueError):
            state.remember(payload, "p", owner=bad)
