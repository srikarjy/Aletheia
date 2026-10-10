"""Hybrid state adapter: fast local memory backed by durable Postgres tables.

The API remains usable in fixture/demo environments where Postgres is unavailable;
the local stores are the graceful fallback. In deployed environments every cache
entry, async job, and completed research run is also persisted to Postgres.
"""

from __future__ import annotations

import os
import time
from threading import RLock
from typing import Any

from psycopg.types.json import Jsonb

from app.db import connect
from app.infrastructure.cache import TTLCache


class _AnyOwner:
    """Sentinel meaning "do not restrict by owner" (admins only)."""

    def __repr__(self) -> str:
        return "ANY_OWNER"


ANY_OWNER = _AnyOwner()
Owner = str | _AnyOwner

# Ownership scoping is a REQUIRED keyword argument on every job/memory read, list and
# delete -- there is deliberately no default. A default of "everyone" would turn each
# forgotten argument into a silent cross-user data leak; a required argument turns it
# into a TypeError the first time the code path runs. Admins pass ANY_OWNER explicitly,
# so reading someone else's data is always a visible decision at the call site.
#
# "Not found" and "not yours" are the same outcome (None / False) *by construction*:
# there is one code path, so the API cannot leak which job ids exist.
# Rows with a NULL owner (created before ownership existed) match no real owner, so
# only ANY_OWNER can see them: legacy data fails closed, it is not claimed by anyone.


def _visible(record_owner: str | None, owner: Owner) -> bool:
    return owner is ANY_OWNER or (record_owner is not None and record_owner == owner)


def _owner_sql(owner: Owner) -> tuple[str, tuple]:
    """Static SQL fragment + params; the owner value only ever travels as a parameter."""
    if owner is ANY_OWNER:
        return "", ()
    return " AND owner_sub = %s", (owner,)


class RuntimeState:
    def __init__(self) -> None:
        ttl = int(os.environ.get("RESPONSE_CACHE_TTL_SECONDS", "21600"))
        size = int(os.environ.get("RESPONSE_CACHE_MAX_SIZE", "512"))
        self.responses: TTLCache[str, dict[str, Any]] = TTLCache(size, ttl)
        self.jobs: TTLCache[str, dict[str, Any]] = TTLCache(
            int(os.environ.get("JOB_STORE_MAX_SIZE", "1000")),
            int(os.environ.get("JOB_STORE_TTL_SECONDS", "86400")),
        )
        self.memories: dict[str, dict[str, Any]] = {}
        self._lock = RLock()
        self._schema_ready = False
        self._last_schema_attempt = 0.0
        self.persistence_available = False

    def ensure_schema(self) -> bool:
        if self._schema_ready:
            return True
        # Avoid hammering a temporarily unavailable database on every poll.
        if time.time() - self._last_schema_attempt < 5:
            return False
        self._last_schema_attempt = time.time()
        try:
            conn = connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(_RUNTIME_SCHEMA)
                conn.commit()
            finally:
                conn.close()
            self._schema_ready = True
            self.persistence_available = True
            return True
        except Exception:
            self.persistence_available = False
            return False

    def get_response(self, cache_key: str) -> dict[str, Any] | None:
        try:
            return self.responses[cache_key]
        except KeyError:
            pass
        if not self.ensure_schema():
            return None
        try:
            conn = connect()
            try:
                with conn.cursor() as cur:
                    cur.execute("DELETE FROM response_cache WHERE expires_at <= now()")
                    cur.execute("SELECT payload FROM response_cache WHERE cache_key = %s", (cache_key,))
                    row = cur.fetchone()
                conn.commit()
            finally:
                conn.close()
            if row:
                self.responses[cache_key] = row[0]
                return row[0]
        except Exception:
            self.persistence_available = False
        return None

    def put_response(self, cache_key: str, payload: dict[str, Any]) -> None:
        self.responses[cache_key] = payload
        if not self.ensure_schema():
            return
        try:
            conn = connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO response_cache (cache_key, payload, expires_at)
                           VALUES (%s, %s, now() + (%s * interval '1 second'))
                           ON CONFLICT (cache_key) DO UPDATE SET payload = EXCLUDED.payload,
                           expires_at = EXCLUDED.expires_at, updated_at = now()""",
                        (cache_key, Jsonb(payload), self.responses.ttl_seconds),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            self.persistence_available = False

    def clear_responses(self) -> int:
        count = len(self.responses)
        self.responses.clear()
        if self.ensure_schema():
            try:
                conn = connect()
                try:
                    with conn.cursor() as cur:
                        cur.execute("DELETE FROM response_cache")
                        count += cur.rowcount
                    conn.commit()
                finally:
                    conn.close()
            except Exception:
                self.persistence_available = False
        return count

    def put_job(self, job_id: str, job: dict[str, Any]) -> None:
        self.jobs[job_id] = job
        if not self.ensure_schema():
            return
        try:
            conn = connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO async_jobs
                           (job_id, status, claim, multi_agent, debate_id, result, error,
                            created_at, started_at, completed_at, owner_sub)
                           VALUES (%s::uuid, %s, %s, %s, %s::uuid, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (job_id) DO UPDATE SET status = EXCLUDED.status,
                           debate_id = EXCLUDED.debate_id, result = EXCLUDED.result,
                           error = EXCLUDED.error, started_at = EXCLUDED.started_at,
                           completed_at = EXCLUDED.completed_at""",
                        (
                            job_id, job["status"], job.get("claim", ""),
                            bool(job.get("multi_agent")), job.get("debate_id"),
                            Jsonb(job["result"]) if job.get("result") else None,
                            job.get("error"), job["created_at"], job.get("started_at"),
                            job.get("completed_at"), job.get("owner"),
                        ),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            self.persistence_available = False

    def get_job(self, job_id: str, *, owner: Owner) -> dict[str, Any] | None:
        try:
            job = self.jobs[job_id]
            return job if _visible(job.get("owner"), owner) else None
        except KeyError:
            pass
        if not self.ensure_schema():
            return None
        try:
            conn = connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """SELECT status, claim, multi_agent, debate_id::text, result, error,
                                  created_at, started_at, completed_at, owner_sub
                           FROM async_jobs WHERE job_id = %s::uuid""",
                        (job_id,),
                    )
                    row = cur.fetchone()
            finally:
                conn.close()
            if row:
                job = dict(zip(
                    ("status", "claim", "multi_agent", "debate_id", "result", "error",
                     "created_at", "started_at", "completed_at", "owner"), row
                ))
                self.jobs[job_id] = job
                return job if _visible(job["owner"], owner) else None
        except Exception:
            self.persistence_available = False
        return None

    def list_jobs(self, limit: int, offset: int, *, owner: Owner) -> tuple[int, list[dict[str, Any]]]:
        if self.ensure_schema():
            try:
                where, params = _owner_sql(owner)
                conn = connect()
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"SELECT count(*) FROM async_jobs WHERE true{where}", params)
                        total = cur.fetchone()[0]
                        cur.execute(
                            f"""SELECT job_id::text, status, claim, debate_id::text, error,
                                      created_at, started_at, completed_at
                               FROM async_jobs WHERE true{where}
                               ORDER BY created_at DESC LIMIT %s OFFSET %s""",
                            (*params, limit, offset),
                        )
                        rows = cur.fetchall()
                finally:
                    conn.close()
                keys = ("job_id", "status", "claim", "debate_id", "error", "created_at", "started_at", "completed_at")
                return total, [dict(zip(keys, row)) for row in rows]
            except Exception:
                self.persistence_available = False
        pairs = sorted(
            ((k, v) for k, v in self.jobs.items() if _visible(v.get("owner"), owner)),
            key=lambda pair: pair[1].get("created_at", 0),
            reverse=True,
        )
        return len(pairs), [{"job_id": key, **value} for key, value in pairs[offset:offset + limit]]

    def delete_job(self, job_id: str, *, owner: Owner) -> bool:
        found = False
        try:
            if _visible(self.jobs[job_id].get("owner"), owner):
                del self.jobs[job_id]
                found = True
        except KeyError:
            pass
        if self.ensure_schema():
            try:
                where, params = _owner_sql(owner)
                conn = connect()
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"DELETE FROM async_jobs WHERE job_id = %s::uuid{where}", (job_id, *params))
                        found = found or cur.rowcount > 0
                    conn.commit()
                finally:
                    conn.close()
            except Exception:
                self.persistence_available = False
        return found

    def remember(self, payload: dict[str, Any], pipeline: str, from_cache: bool = False, *, owner: str) -> None:
        """`owner` is always a concrete subject (who ran the analysis), never ANY_OWNER."""
        if not isinstance(owner, str) or not owner:
            raise ValueError("remember() requires a concrete owner subject")
        debate_id = str(payload["debate_id"])
        memory = {
            "debate_id": debate_id,
            "claim": payload["claim"],
            "verdict": payload["verdict"],
            "confidence": payload["confidence"],
            "pipeline": pipeline,
            "from_cache": from_cache,
            "created_at": time.time(),
            "owner": owner,
            "result": payload,
        }
        with self._lock:
            self.memories[debate_id] = memory
        if not self.ensure_schema():
            return
        try:
            conn = connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        """INSERT INTO research_memory
                           (debate_id, claim, verdict, confidence, pipeline, from_cache, response, owner_sub)
                           VALUES (%s::uuid, %s, %s, %s, %s, %s, %s, %s)
                           ON CONFLICT (debate_id) DO NOTHING""",
                        (debate_id, memory["claim"], memory["verdict"], memory["confidence"],
                         pipeline, from_cache, Jsonb(payload), owner),
                    )
                conn.commit()
            finally:
                conn.close()
        except Exception:
            self.persistence_available = False

    def list_memories(self, limit: int = 20, *, owner: Owner) -> list[dict[str, Any]]:
        if self.ensure_schema():
            try:
                where, params = _owner_sql(owner)
                conn = connect()
                try:
                    with conn.cursor() as cur:
                        cur.execute(
                            f"""SELECT debate_id::text, claim, verdict, confidence, pipeline,
                                      from_cache, extract(epoch from created_at)
                               FROM research_memory WHERE true{where}
                               ORDER BY created_at DESC LIMIT %s""",
                            (*params, limit),
                        )
                        rows = cur.fetchall()
                finally:
                    conn.close()
                keys = ("debate_id", "claim", "verdict", "confidence", "pipeline", "from_cache", "created_at")
                return [dict(zip(keys, row)) for row in rows]
            except Exception:
                self.persistence_available = False
        with self._lock:
            values = sorted(
                (m for m in self.memories.values() if _visible(m.get("owner"), owner)),
                key=lambda item: item["created_at"],
                reverse=True,
            )
            return [{k: v for k, v in item.items() if k not in ("result", "owner")} for item in values[:limit]]

    def get_memory(self, debate_id: str, *, owner: Owner) -> dict[str, Any] | None:
        with self._lock:
            local = self.memories.get(debate_id)
        if local:
            return local["result"] if _visible(local.get("owner"), owner) else None
        if not self.ensure_schema():
            return None
        try:
            where, params = _owner_sql(owner)
            conn = connect()
            try:
                with conn.cursor() as cur:
                    cur.execute(
                        f"SELECT response FROM research_memory WHERE debate_id = %s::uuid{where}",
                        (debate_id, *params),
                    )
                    row = cur.fetchone()
            finally:
                conn.close()
            return row[0] if row else None
        except Exception:
            self.persistence_available = False
            return None

    def delete_memory(self, debate_id: str, *, owner: Owner) -> bool:
        found = False
        with self._lock:
            local = self.memories.get(debate_id)
            if local is not None and _visible(local.get("owner"), owner):
                del self.memories[debate_id]
                found = True
        if self.ensure_schema():
            try:
                where, params = _owner_sql(owner)
                conn = connect()
                try:
                    with conn.cursor() as cur:
                        cur.execute(f"DELETE FROM research_memory WHERE debate_id = %s::uuid{where}", (debate_id, *params))
                        found = found or cur.rowcount > 0
                    conn.commit()
                finally:
                    conn.close()
            except Exception:
                self.persistence_available = False
        return found


_RUNTIME_SCHEMA = """
CREATE TABLE IF NOT EXISTS response_cache (
    cache_key TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS response_cache_expiry_idx ON response_cache (expires_at);

CREATE TABLE IF NOT EXISTS async_jobs (
    job_id UUID PRIMARY KEY,
    status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    claim TEXT NOT NULL,
    multi_agent BOOLEAN NOT NULL DEFAULT false,
    debate_id UUID,
    result JSONB,
    error TEXT,
    created_at DOUBLE PRECISION NOT NULL,
    started_at DOUBLE PRECISION,
    completed_at DOUBLE PRECISION
);
CREATE INDEX IF NOT EXISTS async_jobs_created_idx ON async_jobs (created_at DESC);

CREATE TABLE IF NOT EXISTS research_memory (
    debate_id UUID PRIMARY KEY,
    claim TEXT NOT NULL,
    verdict TEXT NOT NULL,
    confidence DOUBLE PRECISION NOT NULL,
    pipeline TEXT NOT NULL,
    from_cache BOOLEAN NOT NULL DEFAULT false,
    response JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS research_memory_created_idx ON research_memory (created_at DESC);

-- Phase 10b: ownership. Nullable on purpose: rows that predate ownership have NULL and
-- are visible to admins only (fail closed). Not backfilled -- guessing an owner would
-- hand someone else's data to the wrong person.
ALTER TABLE async_jobs ADD COLUMN IF NOT EXISTS owner_sub TEXT;
ALTER TABLE research_memory ADD COLUMN IF NOT EXISTS owner_sub TEXT;
CREATE INDEX IF NOT EXISTS async_jobs_owner_idx ON async_jobs (owner_sub, created_at DESC);
CREATE INDEX IF NOT EXISTS research_memory_owner_idx ON research_memory (owner_sub, created_at DESC);
"""
