# Design

> BLUEPRINT.md says *when*. This says *what* — the concrete contracts each
> phase is built against. Anything marked `PROPOSED` is a draft to argue with,
> not a decision — it becomes fixed only once the linked question in
> [QUESTIONS.md](QUESTIONS.md) is resolved.

---

## Database schema

### `embeddings`

```sql
CREATE TABLE embeddings (
    id            SERIAL PRIMARY KEY,
    paper_id      TEXT NOT NULL,        -- real PubMed ID, not internal
    embedding     VECTOR(1536) NOT NULL, -- PROPOSED: dimension depends on embedding model choice
    metadata      JSONB,                -- title, authors, journal, year
    content       TEXT NOT NULL,        -- abstract or chunk used for embedding
    created_at    TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON embeddings USING ivfflat (embedding vector_cosine_ops);
```

**Why this shape:** `paper_id` is a real PubMed ID so the skeptic can
independently verify it exists — this is the "no hallucinated citations"
guarantee from README made concrete at the schema level.

**PROPOSED / unresolved:** embedding model + dimension not chosen yet.

### `provenance`

```sql
CREATE TABLE provenance (
    id              SERIAL PRIMARY KEY,
    debate_id       UUID NOT NULL,       -- groups every row belonging to one /debate call
    claim           TEXT NOT NULL,
    agent           TEXT NOT NULL,       -- 'advocate' | 'skeptic' | 'synthesizer'
    action          TEXT NOT NULL,       -- e.g. 'retrieve', 'appraise', 'challenge', 'resolve'
    source_paper_id TEXT,                -- FK-ish to embeddings.paper_id, nullable (synthesizer's 'resolve' cites no new paper)
    detail          JSONB,               -- action-specific payload (what was appraised, what was challenged, why)
    prompt_version  TEXT,                -- see Q7 — which prompt produced this action
    timestamp       TIMESTAMPTZ DEFAULT now()
);
CREATE INDEX ON provenance (debate_id);
```

**Why this shape vs. README's original 5-column sketch:** README listed
`claim, agent, source_paper_id, action, timestamp`. Two columns added here
and why:

- `debate_id` — README's version has no way to group all rows belonging to
  one debate transcript into an ordered sequence. Without it you cannot
  reconstruct "the" transcript for a claim if the same claim is ever debated
  twice (e.g. baseline run vs debate run in Phase 6). This is a gap, not a
  gold-plate — flagged as [Q1](QUESTIONS.md#q1) because it changes the
  primary key structure and should be confirmed, not just adopted.
- `prompt_version` — if the advocate's prompt changes between runs, an old
  provenance row silently means something different. Flagged as
  [Q7](QUESTIONS.md#q7).

---

## API contract

### `POST /debate`

**Request:**
```json
{ "claim": "string, required" }
```

**Response:**
```json
{
  "debate_id": "uuid",
  "claim": "string",
  "conclusion": "string",
  "confidence": 0.0,
  "transcript": [
    { "agent": "advocate", "action": "retrieve", "detail": {}, "source_paper_id": "PMID123" },
    { "agent": "advocate", "action": "appraise", "detail": {}, "source_paper_id": "PMID123" },
    { "agent": "skeptic",  "action": "challenge", "detail": {}, "source_paper_id": "PMID123" },
    { "agent": "synthesizer", "action": "resolve", "detail": {}, "source_paper_id": null }
  ],
  "sources": [
    { "paper_id": "PMID123", "title": "string", "used_by": ["advocate", "skeptic"] }
  ]
}
```

**PROPOSED / unresolved:** synchronous vs async — see [Q8](QUESTIONS.md#q8).
If the agent loop + MCP retrieval takes more than a few seconds, this
contract may need to become a job-submission + polling shape instead of a
single blocking call. Not decided; Phase 0's fixture response should still
match this shape so Phase 4 doesn't require a breaking contract change.

---

## Agent interface contract

Every agent (advocate, skeptic, synthesizer) is a function with the same
shape, regardless of internal prompt:

```
Agent(debate_id, claim, transcript_so_far, evidence) -> (new_transcript_rows, agent_output)
```

- **Input:** the claim, everything written to the transcript by prior
  agents, and (for advocate only, initially) freshly retrieved evidence.
- **Output:** one or more provenance rows (never zero — silent steps are
  exactly what README's commandment #2 prohibits) plus a structured output
  object consumed by the next agent or the API response.

**Why one contract for all three roles:** the advocate, skeptic, and
synthesizer are not characters with different APIs — per README they are the
same kind of thing (a cognitive operation over a transcript). A uniform
interface is what makes it possible to add a 4th operation later without
redesigning the loop.

**Open:** exact loop control — who decides when the skeptic is "done"
challenging and synthesis should start? See [Q5](QUESTIONS.md#q5).

---

## MCP retrieval contract (Biolab PubMed)

**VERIFIED 2026-07-13** against the real, running Biolab MCP server — see
[Q2](QUESTIONS.md#q2) for the full resolution and what the earlier assumption
below got wrong.

```
tool: search_pubmed  (MCP stdio transport — spawns `python -m biolab.server`)

search_pubmed(query: str, agent_id: str, max_results: int = 5) -> {
  "query_echo": str,
  "papers": [
    { "pmid": str, "retrieval_id": str, "title": str, "abstract": str }
  ]
}
```

`max_results` is hard-capped at 50 server-side. No `authors`/`year`/`journal`
fields — Biolab deliberately doesn't surface them. `retrieval_id` is per-paper
and is the value that must land in `provenance.retrieval_id` (see
[Q9](QUESTIONS.md#q9) — that column doesn't exist yet). Rate limit is a real,
measured 3 req/sec (unauthenticated NCBI), not a guess.

<details>
<summary>Original unverified assumption (superseded)</summary>

```
biolab.pubmed_search(query: str, max_results: int) -> [
  { paper_id, title, abstract, authors, year, journal }
]
```

Wrong tool name, wrong fields, missing the required `agent_id` param and the
per-paper `retrieval_id`. Kept here as a record of what "invented, not
verified" actually costs when checked against reality.

</details>

---

## Eval harness output contract

**PROPOSED.** Each run (baseline or debate) over the 5-claim set produces:

```json
{
  "run_type": "baseline | debate",
  "claim_id": "string",
  "unsupported_claim_rate": 0.0,   -- see Q6 for definition
  "citation_accuracy": 0.0,
  "confidence_calibration_error": 0.0  -- see Q4 for definition
}
```

The comparison notebook in Phase 6 diffs `baseline` rows against `debate`
rows per claim, then aggregates. Both metric *definitions* are open —
this is only the shape of the output, not proof the metrics are well-defined
yet.
