# Open Questions

> Per STAFF_ENGINEER.md Rule 8/9: no architecture decision gets adopted by
> default. Every entry here blocks a specific phase in [BLUEPRINT.md](BLUEPRINT.md)
> until it has a real answer with a stated justification — not a guess.
>
> Status legend: `OPEN` — unresolved, blocking. `DECIDED` — answered below,
> with the justification you should be able to defend out loud.

---

### Q3 — Claim selection criteria for the 5-claim eval set {#q3}

**Status:** OPEN
**Blocks:** Phase 5, Phase 6

"5 curated scientific claims" (README) begs the question: curated by what
rule? Candidates:
- Claims with genuinely conflicting published evidence (stress-tests the
  skeptic's conflict-resolution role)
- Claims with a known ground-truth verdict (lets you score accuracy, not
  just internal consistency)
- A mix, deliberately including at least one claim with no clean resolution
  (tests whether the synthesizer honestly reports "unresolved" instead of
  fabricating confidence)

**Riskiest assumption:** if all 5 claims have easy, uncontested evidence, the
eval proves nothing about the debate loop's actual value proposition — the
skeptic role would never have anything real to challenge.

---

### Q4 — What does "confidence calibration" mean here? {#q4}

**Status:** OPEN
**Blocks:** Phase 4, Phase 6

Confidence calibration normally means: over many predictions, a stated
confidence of 0.7 should be correct ~70% of the time. That requires many
claims with known outcomes — 5 claims is nowhere near enough for a real
calibration curve. So what is Phase 6 actually going to report?

- A weaker proxy (e.g. "did the synthesizer's confidence go down on the
  claim we know is contested"), acknowledged as a proxy, not true calibration?
- Or is the metric name in README aspirational and the real Phase 6 output
  should be reframed?

**Riskiest assumption:** shipping a "confidence_calibration_error" number in
the eval output without first deciding what it measures produces a number
that looks rigorous and isn't. Per Rule 12 (be brutally honest) — resolve
this before Phase 6, not after, so the eval notebook doesn't launder an
undefined metric into a false conclusion.

---

### Q5 — Debate loop termination {#q5} — DECIDED 2026-07-13

**Decision:** Fixed pipeline. Advocate → skeptic → synthesizer, exactly one
pass each, no back-and-forth. `Agent(debate_id, claim, transcript_so_far,
evidence) -> (new_transcript_rows, agent_output)` needs no "done" signal —
the orchestrator calls each agent exactly once, in order.

**Justification:** no measured evidence exists yet that a single skeptic pass
leaves real challenges unaddressed — that evidence can only come from Phase
6's eval data, which doesn't exist until Phase 6 runs. A bounded or
convergence loop adds real complexity now (round counters, a "done vs new
challenge" signal, unpredictable latency/cost) against a requirement that
hasn't been demonstrated. It also directly serves Phase 6: a fixed pipeline
produces bounded, comparable runs across the 5-claim eval set, whereas a
variable-length loop makes baseline-vs-debate comparison noisier and
threatens Q8 (sync vs async `/debate`) sooner than necessary, since a bounded
3-call pipeline has predictable worst-case latency and an open-ended
convergence loop doesn't.

**Revisit trigger:** if Phase 6's eval data shows single-pass debate doesn't
meaningfully reduce the unsupported-claim rate vs baseline, that's the real,
measured signal to introduce a bounded/convergence loop — not before.

---

### Q6 — Definition of "unsupported claim" for the eval metric {#q6}

**Status:** OPEN
**Blocks:** Phase 6

Two very different implementations both look like "unsupported claim rate":
- **Mechanical check:** does every assertion in the conclusion cite a
  `source_paper_id` present in provenance? (Cheap, deterministic, but only
  catches missing citations — not citations that misrepresent the source.)
- **LLM-judge check:** does an independent model verify the cited paper
  actually supports the specific assertion? (Catches misrepresentation, but
  introduces a second LLM's own hallucination risk into the metric itself.)

**Riskiest assumption:** picking the mechanical check because it's easier
to implement, without acknowledging it only measures "did we cite something,"
not "was the citation honest" — which is the actual thing README claims to
solve.

---

### Q7 — Prompt versioning {#q7} — DECIDED 2026-07-13

**Decision:** `prompt_version` is a hash of the actual prompt template text
at call time (first 12 hex chars of SHA-256), computed automatically in code
— not a hand-bumped string tag.

**Justification:** the doc's own riskiest-assumption callout was that a human
has to remember to bump a version string every time a prompt changes, and one
missed bump makes old provenance rows silently misleading — exactly the
failure mode README's commandment #2 ("no silent steps") exists to prevent.
Hashing the template removes the human step entirely: the value in
`prompt_version` is always accurate because it's derived from the actual text
that ran, not asserted by someone editing a version number nearby. A
provenance row stays self-contained and honest even if the prompt file is
later edited or deleted — the hash on the row is a fact about what actually
ran, not a claim that has to be trusted.

---

### Q8 — Synchronous vs async `/debate` endpoint {#q8}

**Status:** OPEN
**Blocks:** Phase 4 (only if latency proves untenable)

A full advocate → skeptic → synthesizer pass, each potentially calling an
LLM and possibly MCP retrieval, could take well past what's comfortable for
a single blocking HTTP request. Is `POST /debate` staying synchronous
(simplest, matches DESIGN.md's current contract), or does it need to become
submit-job + poll-for-result?

**Riskiest assumption:** assuming synchronous is fine without ever measuring
actual latency in Phase 4. Per README's commandment #1 — don't add this
infrastructure (job queue, polling endpoint) until a real request actually
times out. This question stays OPEN and low-priority until Phase 4 produces
a real latency number; do not pre-solve it in Phase 0.

---

## Resolved

### Q1 — Provenance table keys {#q1} — DECIDED 2026-07-10

**Decision:** `provenance` gets an explicit `debate_id UUID NOT NULL` column,
generated once per `/debate` call, not a `(claim, timestamp)` composite key.

**Justification:** Phase 6 requires debating the *same claim string* twice —
once as single-model baseline, once through the debate loop — to produce a
comparison. A `(claim, timestamp)` key relies on timestamp uniqueness to tell
those two runs apart, which breaks the moment two runs land close together or
a claim gets re-run for debugging. `debate_id` makes grouping explicit and
independent of wall-clock timing. Confirmed by the user 2026-07-10; no
constraint surfaced that would make the composite key preferable (i.e.
re-running a claim is expected, not an edge case).

---

### Q2 — Biolab MCP tool contract {#q2} — DECIDED 2026-07-13

**Decision:** verified against the real, running Biolab MCP server (built and
tested in the same portfolio, `github.com/srikarjy/biolab-mcp-server`) — not
inferred from README, and not the shape DESIGN.md guessed.

Real contract:

```
tool: search_pubmed
transport: MCP stdio (spawns `python -m biolab.server`, not HTTP/SSE)

input:
  query: str        # required
  agent_id: str      # required — Aletheia must pass one, e.g. "aletheia:advocate"
  max_results: int   # optional, default 5, hard-capped at 50 (raises ValueError outside [1,50])

output:
  {
    "query_echo": str,
    "papers": [
      { "pmid": str, "retrieval_id": str, "title": str, "abstract": str }
    ]
  }
```

**What DESIGN.md got wrong:** assumed tool name `pubmed_search` (real name is
`search_pubmed`), assumed `authors`/`year`/`journal` fields (Biolab doesn't
return them — its schema deliberately keeps only `pmid`/`title`/`abstract` in
the tool output, with everything else preserved in a raw snapshot server-side,
not surfaced to callers), and didn't account for the required `agent_id` param
or the per-paper `retrieval_id` (this is the field Aletheia's `provenance`
table needs to store — see the new gap this surfaced, tracked as Q9 below).

**Measured, not estimated:** PubMed's underlying rate limit for unauthenticated
callers is 3 req/sec — this was actually hit (`HTTPError: 429`) during Biolab's
own test suite, not assumed. Phase 1's retrieval code should not fire
concurrent/rapid-fire calls without accounting for this.

---

### Q9 — provenance table is missing retrieval_id {#q9} — DECIDED 2026-07-13

**Decision:** added `retrieval_id TEXT` (nullable — not every provenance row
comes from a retrieval) to `provenance`, both via `ALTER TABLE` on the live
Postgres instance and in `db/init.sql` for future fresh installs.

**Justification:** found while resolving Q2, not previously flagged anywhere:
`provenance` (already migrated live in Postgres, Phase 0) had
`source_paper_id` but no `retrieval_id` column. Biolab's entire premise — the
reason it exists instead of Aletheia just calling PubMed directly — is that
`retrieval_id` is the link between "what Aletheia used" and "the exact,
timestamped, audit-logged retrieval that produced it." Without this column,
Phase 1 could persist `source_paper_id` but had nowhere to put the value that
makes the whole cross-project provenance chain real. Verified: real
`retrieval_id` values from Biolab now land in this column on every Phase 1
retrieval (`scripts/run_phase1.py`).

---

### Q10 — ivfflat index on embeddings, built empty, silently broken {#q10} — DECIDED 2026-07-13

**Decision:** dropped `embeddings_vector_idx` (the `ivfflat` index from Phase
0's `db/init.sql`) entirely, from both the live DB and the schema file. Not
reindexed and kept — removed.

**What happened:** Phase 1's exit criteria requires proving `embeddings` rows
are "queryable back by similarity." The first real similarity query
(`SELECT ... ORDER BY embedding <=> $1 LIMIT 3`) returned **zero rows** — no
error, just silently wrong — despite the table genuinely having 10 rows
(confirmed by a plain `SELECT count(*)`, which worked fine). Root cause: the
`ivfflat` index was created in Phase 0's `db/init.sql`, which runs once via
Postgres's `docker-entrypoint-initdb.d` when the container first starts —
i.e., before any rows existed. `ivfflat` is a clustering index that trains on
whatever data is present at build time; trained on zero rows, it produces
degenerate clusters and can silently return an empty ANN result set even
after real data is inserted later, without erroring. Confirmed directly:
running `REINDEX INDEX embeddings_vector_idx` printed Postgres's own notice —
*"ivfflat index created with little data... This will cause low recall...
Drop the index until the table has more data."* Disabling the index scan
(`SET LOCAL enable_indexscan = off`) immediately fixed the query, proving the
index — not the query, not psycopg, not pgvector's operators — was the cause.

**Justification for dropping instead of just reindexing:** Postgres's own
hint says exactly this ("drop the index until the table has more data"), and
at this project's real scale (a 5-claim eval set, tens of rows for the
foreseeable phases) sequential scan is fast and exact — an approximate index
buys nothing here and reintroduces the same failure mode after every future
bulk load unless someone remembers to `REINDEX` each time. Per this project's
own rule (don't add infrastructure until a real query fails without it): add
the index back only when a real query is measured to be slow because of table
size, not preemptively.

**Why this is worth having ready for an interview:** it's a concrete example
of "index existed, schema looked right, query looked right, and the system
was still silently wrong" — the kind of failure mode that doesn't show up
until you actually run a real query against real data, which is this
project's whole operating discipline.
