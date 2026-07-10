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
CREATE INDEX embeddings_vector_idx ON embeddings USING ivfflat (embedding vector_cosine_ops);

CREATE TABLE provenance (
    id              SERIAL PRIMARY KEY,
    debate_id       UUID NOT NULL,
    claim           TEXT NOT NULL,
    agent           TEXT NOT NULL,
    action          TEXT NOT NULL,
    source_paper_id TEXT,
    detail          JSONB,
    prompt_version  TEXT,
    timestamp       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX provenance_debate_id_idx ON provenance (debate_id);
