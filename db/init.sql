-- Phase 0 schema, per DESIGN.md. Applied automatically by the pgvector
-- Docker image on first container start (docker-entrypoint-initdb.d).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE embeddings (
    id            SERIAL PRIMARY KEY,
    paper_id      TEXT NOT NULL,
    embedding     VECTOR(1536) NOT NULL,
    metadata      JSONB,
    content       TEXT NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT now()
);
-- No ivfflat index yet, deliberately. Found during Phase 1 (2026-07-13): an ivfflat
-- index built while this table is empty trains on zero rows and silently returns 0
-- results on ORDER BY <=> LIMIT queries after data is inserted, even though the
-- table isn't empty anymore — Postgres's own NOTICE on REINDEX says as much ("ivfflat
-- index created with little data... Drop the index until the table has more data").
-- At the scale this project runs at (a 5-claim eval set), sequential scan is fast and
-- always correct. Add the index back only when a real query is measured to be slow
-- because of table size, not preemptively.

CREATE TABLE provenance (
    id              SERIAL PRIMARY KEY,
    debate_id       UUID NOT NULL,
    claim           TEXT NOT NULL,
    agent           TEXT NOT NULL,
    action          TEXT NOT NULL,
    source_paper_id TEXT,
    retrieval_id    TEXT,  -- Biolab's audit-trail link, added Q9 (QUESTIONS.md#q9);
                            -- nullable because not every provenance row (e.g. a
                            -- "conclude" or "critique" action) comes from a retrieval
    detail          JSONB,
    prompt_version  TEXT,
    timestamp       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX provenance_debate_id_idx ON provenance (debate_id);

-- Runtime infrastructure: a durable L2 response cache, restart-safe async job
-- metadata, and user-facing research memory. The API keeps a bounded TTL L1
-- cache in-process and treats these tables as the durable source of truth.
CREATE TABLE response_cache (
    cache_key    TEXT PRIMARY KEY,
    payload      JSONB NOT NULL,
    expires_at   TIMESTAMPTZ NOT NULL,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX response_cache_expiry_idx ON response_cache (expires_at);

CREATE TABLE async_jobs (
    job_id       UUID PRIMARY KEY,
    status       TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
    claim        TEXT NOT NULL,
    multi_agent  BOOLEAN NOT NULL DEFAULT false,
    debate_id    UUID,
    result       JSONB,
    error        TEXT,
    created_at   DOUBLE PRECISION NOT NULL,
    started_at   DOUBLE PRECISION,
    completed_at DOUBLE PRECISION
);
CREATE INDEX async_jobs_created_idx ON async_jobs (created_at DESC);

CREATE TABLE research_memory (
    debate_id   UUID PRIMARY KEY,
    claim       TEXT NOT NULL,
    verdict     TEXT NOT NULL,
    confidence  DOUBLE PRECISION NOT NULL,
    pipeline    TEXT NOT NULL,
    from_cache  BOOLEAN NOT NULL DEFAULT false,
    response    JSONB NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX research_memory_created_idx ON research_memory (created_at DESC);
