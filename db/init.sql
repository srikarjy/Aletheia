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
