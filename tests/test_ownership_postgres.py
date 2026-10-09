"""Phase 10b against REAL Postgres: the column migration and the SQL ownership scoping.

The in-memory tests in test_ownership.py cannot see SQL mistakes, and RuntimeState
silently falls back to memory when a query throws -- so a SQL bug there would still
pass. These tests therefore (a) read through a FRESH RuntimeState so the L1 cache
cannot answer, and (b) assert persistence_available and inspect the table directly.

Opt-in because it needs a database:
    TEST_DATABASE_URL=postgresql://.../aletheia_test poetry run pytest tests/test_ownership_postgres.py

The fixture DROPS async_jobs and research_memory. It refuses to run unless the database
name ends in "test", so pointing it at a real database by mistake does nothing.
"""
import os
import time
from uuid import uuid4

import psycopg
import pytest

from app.infrastructure.state import ANY_OWNER, RuntimeState

URL = os.environ.get("TEST_DATABASE_URL", "")
pytestmark = pytest.mark.skipif(not URL, reason="set TEST_DATABASE_URL (a scratch database whose name ends in 'test')")

ALICE, BOB = "alice@bu.edu", "bob@bu.edu"

LEGACY_SCHEMA = """
CREATE TABLE async_jobs (
    job_id UUID PRIMARY KEY, status TEXT NOT NULL, claim TEXT NOT NULL,
    multi_agent BOOLEAN NOT NULL DEFAULT false, debate_id UUID, result JSONB, error TEXT,
    created_at DOUBLE PRECISION NOT NULL, started_at DOUBLE PRECISION, completed_at DOUBLE PRECISION
);
CREATE TABLE research_memory (
    debate_id UUID PRIMARY KEY, claim TEXT NOT NULL, verdict TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL, pipeline TEXT NOT NULL,
    from_cache BOOLEAN NOT NULL DEFAULT false, response JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def raw():
    return psycopg.connect(URL)


@pytest.fixture
def fresh_db(monkeypatch):
    dbname = psycopg.conninfo.conninfo_to_dict(URL).get("dbname", "")
    if not dbname.endswith("test"):
        pytest.fail(f"refusing to drop tables in database {dbname!r}: name must end in 'test'")
    monkeypatch.setenv("DATABASE_URL", URL)
    # connect() registers the pgvector type; these tables don't use it, so don't require it.
    monkeypatch.setattr("app.db.register_vector", lambda conn: None)
    with raw() as c:
        c.execute("DROP TABLE IF EXISTS async_jobs, research_memory")
    yield


def new_state() -> RuntimeState:
    """A RuntimeState with empty L1 caches, so every read must go to SQL."""
    state = RuntimeState()
    assert state.ensure_schema() is True, "could not reach/initialise the test database"
    return state


def job(owner, claim="c", **extra):
    return {"status": "completed", "claim": claim, "created_at": time.time(), "owner": owner, **extra}


def payload(claim="c"):
    return {"debate_id": str(uuid4()), "claim": claim, "verdict": "unresolved", "confidence": 0.5}


def count(table, where="true", params=()):
    with raw() as c:
        return c.execute(f"SELECT count(*) FROM {table} WHERE {where}", params).fetchone()[0]


# --- migration ----------------------------------------------------------------

def test_migration_adds_owner_column_and_leaves_legacy_rows_unowned(fresh_db):
    legacy_job, legacy_mem = str(uuid4()), str(uuid4())
    with raw() as c:
        c.execute(LEGACY_SCHEMA)
        c.execute("INSERT INTO async_jobs (job_id, status, claim, created_at) VALUES (%s,'completed','old',1.0)", (legacy_job,))
        c.execute(
            "INSERT INTO research_memory (debate_id, claim, verdict, confidence, pipeline, response) "
            "VALUES (%s,'old','unresolved',0.5,'single_call','{}')", (legacy_mem,),
        )
    state = new_state()  # runs the migration against tables that pre-date owner_sub
    assert count("async_jobs", "owner_sub IS NULL") == 1
    assert count("research_memory", "owner_sub IS NULL") == 1
    # unowned rows: invisible to a student, visible to an admin
    assert new_state().get_job(legacy_job, owner=ALICE) is None
    assert new_state().get_job(legacy_job, owner=ANY_OWNER) is not None
    assert state.persistence_available is True


def test_schema_migration_is_idempotent(fresh_db):
    new_state()
    new_state()
    new_state()


# --- jobs: scoping done by SQL ------------------------------------------------

def test_job_owner_is_persisted_and_reads_are_scoped_in_sql(fresh_db):
    writer = new_state()
    a, b = str(uuid4()), str(uuid4())
    writer.put_job(a, job(ALICE))
    writer.put_job(b, job(BOB))
    assert count("async_jobs", "owner_sub = %s", (ALICE,)) == 1  # really in the table
    reader = new_state()
    assert reader.get_job(a, owner=ALICE) is not None
    assert reader.get_job(a, owner=BOB) is None
    assert reader.get_job(a, owner=ANY_OWNER) is not None


def test_list_and_count_are_scoped_and_paginate_within_the_owner(fresh_db):
    writer = new_state()
    for i in range(5):
        writer.put_job(str(uuid4()), job(ALICE, claim=f"a{i}", created_at=100.0 + i))
    for i in range(3):
        writer.put_job(str(uuid4()), job(BOB, claim=f"b{i}", created_at=200.0 + i))
    reader = new_state()
    total, page = reader.list_jobs(2, 0, owner=ALICE)
    assert total == 5 and [j["claim"] for j in page] == ["a4", "a3"]
    total, page = reader.list_jobs(2, 4, owner=ALICE)
    assert total == 5 and [j["claim"] for j in page] == ["a0"]  # offset never leaks into bob's rows
    assert reader.list_jobs(50, 0, owner=BOB)[0] == 3
    assert reader.list_jobs(50, 0, owner=ANY_OWNER)[0] == 8


def test_delete_is_scoped_in_sql(fresh_db):
    writer = new_state()
    j = str(uuid4())
    writer.put_job(j, job(ALICE))
    assert new_state().delete_job(j, owner=BOB) is False
    assert count("async_jobs", "job_id = %s::uuid", (j,)) == 1  # survived
    assert new_state().delete_job(j, owner=ALICE) is True
    assert count("async_jobs", "job_id = %s::uuid", (j,)) == 0


def test_owner_cannot_be_changed_by_a_later_write(fresh_db):
    """put_job upserts on every status change. If the owner column were updated on
    conflict, whoever wrote last could take over the job."""
    state = new_state()
    j = str(uuid4())
    state.put_job(j, job(ALICE, status="pending"))
    state.put_job(j, job("mallory@evil.test", status="completed"))
    with raw() as c:
        owner, status = c.execute("SELECT owner_sub, status FROM async_jobs WHERE job_id=%s::uuid", (j,)).fetchone()
    assert (owner, status) == (ALICE, "completed")  # status updated, owner untouched


@pytest.mark.parametrize("hostile", ["x' OR '1'='1", "alice@bu.edu' --", "'; DROP TABLE async_jobs; --", "%", "alice@bu.edu%"])
def test_owner_value_is_a_parameter_never_sql(fresh_db, hostile):
    writer = new_state()
    j = str(uuid4())
    writer.put_job(j, job(ALICE))
    reader = new_state()
    assert reader.list_jobs(50, 0, owner=hostile) == (0, [])
    assert reader.get_job(j, owner=hostile) is None
    assert reader.delete_job(j, owner=hostile) is False
    assert count("async_jobs") == 1  # table intact, row intact


# --- memory --------------------------------------------------------------------

def test_memory_owner_is_persisted_and_scoped_in_sql(fresh_db):
    writer = new_state()
    pa, pb = payload("a"), payload("b")
    writer.remember(pa, "single_call", owner=ALICE)
    writer.remember(pb, "single_call", owner=BOB)
    assert count("research_memory", "owner_sub = %s", (ALICE,)) == 1
    reader = new_state()
    assert reader.get_memory(pa["debate_id"], owner=ALICE) == pa
    assert reader.get_memory(pa["debate_id"], owner=BOB) is None
    assert [m["claim"] for m in reader.list_memories(10, owner=BOB)] == ["b"]
    assert len(reader.list_memories(10, owner=ANY_OWNER)) == 2


def test_memory_delete_is_scoped_in_sql(fresh_db):
    writer = new_state()
    p = payload()
    writer.remember(p, "single_call", owner=ALICE)
    assert new_state().delete_memory(p["debate_id"], owner=BOB) is False
    assert count("research_memory") == 1
    assert new_state().delete_memory(p["debate_id"], owner=ALICE) is True
    assert count("research_memory") == 0
