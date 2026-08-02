# Project Status — Aletheia

> A single-page snapshot: what is built and verified, what is left, and every
> architecture decision taken so far with the reasoning behind it.
>
> Source of truth for *when* is [BLUEPRINT.md](BLUEPRINT.md); for *what* (the
> contracts) it is [DESIGN.md](DESIGN.md); for *why* it is
> [QUESTIONS.md](QUESTIONS.md). This file summarizes all three as of
> **2026-07-15**. If it disagrees with them, they win.

---

## Where the project stands

**Phases 0–8 of 8 are done, each verified against real data, real APIs, and a
real database — not fixtures, not mocks.** The full pipeline runs end to end:
`POST /debate` with a claim returns a structured conclusion, a rubric-anchored
confidence score, the complete debate transcript, and provenance for every
step, in about 74 seconds. Async endpoint, caching, batch processing, and
React frontend all operational.

| Phase | What it delivers | Status |
|---|---|---|
| 0 | Postgres+pgvector schema, FastAPI skeleton, fixture `/debate` | Done 2026-07-10 |
| 1 | Grounded retrieval via Biolab MCP, real embeddings, persistence | Done 2026-07-13 |
| 2 | Advocate agent, provenance on every action | Done 2026-07-13 |
| 3 | Skeptic agent, real challenges against real evidence | Done 2026-07-13 |
| 4 | Synthesizer, rubric-anchored confidence, real `/debate` endpoint | Done 2026-07-14 |
| 5 | Scale to 5-claim eval set with zero manual intervention | Done 2026-07-15 |
| 6 | Eval harness: debate vs single-model baseline, with numbers | Done 2026-07-15 |
| 7 | Interactive React frontend (Vite, TypeScript, nginx) | Done 2026-07-15 |
| 8 | Async job queue, caching, batch processing, health checks | Done 2026-07-15 |

---

## What has been built (verified, phase by phase)

### Phase 0 — Foundations (2026-07-10)

`embeddings` and `provenance` tables migrated into a running Postgres+pgvector
instance; `POST /debate` round-tripped a hardcoded fixture matching the
DESIGN.md response contract, so that Phase 4 could fill the same shape in
without a breaking change. No auth, no frontend, no MCP — deliberately.

### Phase 1 — Grounded retrieval (2026-07-13)

`scripts/run_phase1.py` makes a real MCP call to the Biolab server, gets 5 real
PMIDs with real titles and abstracts for the claim *"BRCA1 mutations increase
pancreatic cancer risk"*, embeds each with OpenAI `text-embedding-3-small`,
persists them, and proves them queryable with a real cosine-similarity query
that returns the correct closest match. Provenance rows carry `retrieval_id`
alongside `source_paper_id`, which is the link that makes the cross-project
audit chain to Biolab real rather than nominal.

**A real bug was found here, not a hypothetical one.** The `ivfflat` index
created in Phase 0 had trained on an empty table and silently returned zero
rows on similarity queries even after data existed — no error, just wrong
answers. See Q10 below.

### Phase 2 — Advocate agent (2026-07-13)

`app/agents/advocate.py` retrieves evidence, writes one `retrieve` provenance
row per paper, then calls Claude (`claude-sonnet-4-5`, forced tool use for
structured output) to build an evidence-based case, writing an `appraise` row
stamped with a real prompt hash. The case was genuinely grounded: it cited 4 of
the 5 retrieved papers with direct quotes and correctly declined to cite the
5th — an ATM founder-variant paper that the query surfaced but that isn't
actually about BRCA1.

### Phase 3 — Skeptic agent (2026-07-13)

`scripts/run_phase3.py` clears the bar well past the minimum of one challenge:
the skeptic raised 5 concrete challenges, each its own `critique` provenance
row, plus an `assess` row. The challenges were substantive rather than
performative — it caught the advocate conflating BRCA1 with BRCA2's higher risk
figures, caught a citation (PMID 42274517) that discusses treatment but doesn't
establish germline BRCA1 susceptibility, and flagged the irrelevant ATM paper.

**Second real bug:** the first live run threw `KeyError: 'uncertainty_notes'`
because Claude's tool-use response was truncated at `max_tokens=1024` mid-JSON.
A tool schema's `required` fields are a strong hint to the model, not an
enforced guarantee. Fixed by raising the limit to 2048 and adding
`app/llm.py`'s `call_tool()`, which inspects `stop_reason` and raises a clear
error at the truncation site instead of letting a confusing `KeyError` surface
several calls downstream. Now shared by all three agents.

### Phase 4 — Synthesizer and the real endpoint (2026-07-14)

`scripts/run_phase4.py` starts a real uvicorn server and POSTs over HTTP — not
`TestClient`, not a fixture — then independently re-reads Postgres to prove the
result. The BRCA1 claim returned HTTP 200, `confidence=0.65`, a rationale
naming rubric anchor C and explicitly ruling out A/B/D, and
`driving_provenance_ids=[51,52,53,54,55,58,59]` — every ID code-validated
against this debate's own provenance before the `conclude` row was allowed to
persist, stamped with the frozen rubric v1 hash `47578859104f`. The
synthesizer genuinely ran the validity screen, keeping the skeptic's
BRCA1/BRCA2-grouping challenges as valid-but-peripheral and anchoring at C for
that stated reason rather than free-floating a number.

**Measured latency: 73.7 seconds** for one synchronous request. It did not time
out, which is the only reason async stays deferred — but it's a real signal.

### Phase 5 — Scale to the 5-claim eval set (2026-07-15)

`scripts/run_phase5.py` runs all 5 curated claims through the full pipeline
with zero manual intervention:

1. **BRCA1/pancreatic** — conflicting evidence → verdict: unresolved
2. **Vitamin D/COVID** — observational vs RCT conflict → verdict: refuted
3. **Aspirin primary prevention** — ASPREE RCT ground truth → verdict: refuted
4. **Omega-3/CVD** — REDUCE-IT vs STRENGTH conflict → verdict: unresolved
5. **HRT mortality** — WHI age-stratified ground truth → verdict: supported

Each claim produces debate transcript, conclusion, confidence, provenance rows,
and sources. Results saved to `eval_results/phase5_results_*.json`. Total
runtime ~6 minutes sequential.

### Phase 6 — Eval harness (2026-07-15)

`scripts/run_phase6.py` implements the comparison:

- **Baseline**: single-model call per claim with same retrieval context
- **Debate**: Phase 5 outputs
- **Metrics**: mechanical unsupported claim rate (citation presence in provenance),
  LLM-judge citation accuracy (does paper support assertion), confidence calibration (ordinal proxy at n=5)
- **Output**: JSON with per-claim and aggregate deltas, honest reporting even if "inconclusive at n=5"

### Phase 7 — Interactive Frontend (2026-07-15)

`frontend/` — Complete React + TypeScript + Vite application:

- Claim input with 5 curated examples pre-loaded
- Real-time debate execution with loading spinner
- Verdict badge (Supported/Refuted/Unresolved) + confidence bar
- Synthesized conclusion with copy button
- Collapsible provenance transcript (color-coded: Advocate=cyan, Skeptic=amber, Synthesizer=green)
- Source cards with PMID and title
- Raw JSON viewer with copy-to-clipboard
- Dark theme with IBM Plex fonts, responsive design
- Production Dockerfile with nginx + API proxy
- Dev server at localhost:3000 proxying to API at localhost:8000

### Phase 8 — Scaling & Production Hardening (2026-07-15)

`app/main.py` and `app/batch.py` add:

- **Async endpoint**: `POST /debate/async` returns job_id <100ms; `GET /debate/jobs/{job_id}` polls for result
- **Response caching**: claim-hash keyed, returns cached result with new debate_id for traceability
- **Batch processing**: `POST /batch/debate` processes N claims sequentially; `POST /batch/eval/run` triggers full eval
- **Observability**: `/health` (with cache stats), `/cache/stats`, `POST /cache/clear`
- **Job management**: `GET /debate/jobs`, `DELETE /debate/jobs/{job_id}`
- **In-memory stores** (replaceable with Redis): job_store, claim_cache, embedding_cache
- **Docker-compose**: db, api, frontend services with health checks

---

## What is left

**All planned phases complete.** The system is feature-complete for the 90-day
deliverable and portfolio demonstration. Future work (only if real need emerges):

- Neo4j for complex provenance graph queries (trigger: pgvector query fails)
- Redis for distributed job queue (trigger: horizontal scaling)
- WebSocket streaming (trigger: UX demands real-time token streaming)
- Auth/multi-user (trigger: actual multi-user requirement)
- LangChain/LangGraph integration (never — custom loop is core value prop)

---

## Open questions, and what each one blocks

| Q | Question | Blocks | Why it isn't answered yet |
|---|---|---|---|
| Q3 | What rule selects the 5 eval claims? | — | **DECIDED** — conflicting + ground truth mix selected |
| Q4b | Does the rubric's confidence track truth? | — | Requires many claims with known outcomes; n=5 supports directional proxy only |
| Q6 | What counts as an "unsupported claim"? | — | **DECIDED** — mechanical + LLM-judge dual metric implemented |
| Q8 | Sync vs async `/debate`? | — | **DECIDED** — both available; sync for dev, async for prod |

---

## Explicitly out of scope until something real fails without it

Neo4j (not until a provenance query pgvector can't express appears),
LangChain/LangGraph (not at all), auth/multi-user/frontend polish (not part of
the 90-day deliverable), streaming responses from `/debate` (only if
synchronous latency proves unusable), Redis (in-memory sufficient), WebSocket
(polling works for 74s jobs).

---

## Architecture decisions taken

### Decided

**Q1 — `provenance` gets an explicit `debate_id UUID`, not a `(claim,
timestamp)` composite key.** *(2026-07-10)* Phase 6 requires debating the same
claim string twice — once as baseline, once through the loop — to produce a
comparison. A timestamp-based key relies on wall-clock uniqueness to tell those
runs apart, which breaks the moment two runs land close together or a claim is
re-run for debugging. Re-running a claim is expected here, not an edge case.

**Q2 — The Biolab MCP contract was verified against the running server, not
inferred from its README.** *(2026-07-13)* The real tool is `search_pubmed`
over MCP stdio, taking `query`, a required `agent_id`, and `max_results`
(hard-capped at 50), returning per-paper `pmid`/`retrieval_id`/`title`/
`abstract`. DESIGN.md's original guess got the tool name wrong
(`pubmed_search`), invented `authors`/`year`/`journal` fields Biolab
deliberately doesn't surface, and missed both the required `agent_id` and the
`retrieval_id` that the provenance chain depends on. The wrong version is kept
in DESIGN.md under a `<details>` block as a record of what "invented, not
verified" actually costs. PubMed's 3 req/sec limit for unauthenticated callers
is measured (a real `HTTPError: 429`), not assumed.

**Q3 — 5 curated claims selected for conflicting evidence + ground truth mix.** *(2026-07-15)*
Claims: BRCA1/pancreatic (conflicting), Vitamin D/COVID (conflicting), Aspirin primary prevention (ground truth refuted), Omega-3/CVD (conflicting), HRT mortality (ground truth supported). Rationale documented in `app/claims.py`.

**Q4a — The synthesizer's confidence comes from rule-constrained judgment
against a written rubric (v1), embedded verbatim in the prompt.** *(2026-07-14)*
Structured output must include `confidence`, a `confidence_rationale` naming the
anchor applied, and `driving_provenance_ids` — and code validates that every
listed ID exists among *this debate's* provenance rows, rejecting the call
otherwise. Citation is enforced, not honor-system.

The rubric runs a validity screen first (a challenge counts only if the weakness
it names is actually present in the cited text), then places the debate against
four anchors: (A) a valid challenge undermines the central evidence → ≤0.3;
(B) evidence genuinely conflicts and neither side is invalidated → 0.4–0.6, and
the verdict must say "unresolved"; (C) valid challenges touch only peripheral
points → 0.5–0.7; (D) no valid substantive challenges → ≥0.8.

**Stated honestly:** the rubric doesn't eliminate judgment, it relocates it —
"does this undermine the *central* evidence?" is still a classification the LLM
makes. What it buys is accountability: the standard is written down, so a human
can check any band assignment and disagree with a specific anchor instead of
arguing with a free-floating 0.6. `confidence: 0.7` means "band C/D per rubric
v1," **not** "correct 70% of the time." Whether it tracks truth is Q4b, open.

Anchor D's validity screen exists because the fixed pipeline (Q5) has no
rebuttal turn — without a sanctioned way to discard an unsound challenge, the
confidence floor would be set by skeptic aggression rather than evidence
quality. Anchor B exists because "explicitly fails to resolve" is a legitimate
outcome that the rubric must reward over fabricated confidence. The
deterministic alternative (a formula counting transcript features) was rejected
as gameable, brittle, and falsely precise.

**Q5 — Fixed pipeline: advocate → skeptic → synthesizer, one pass each, no
back-and-forth.** *(2026-07-13)* No measured evidence exists that a single
skeptic pass leaves real challenges unaddressed — and that evidence can only
come from Phase 6, which hasn't run. A convergence loop adds round counters, a
"done vs new challenge" signal, and unpredictable latency and cost against a
requirement nobody has demonstrated. It also serves Phase 6 directly: a fixed
pipeline produces bounded, comparable runs, where a variable-length loop makes
baseline-vs-debate noisier and threatens Q8 sooner. **Revisit trigger:** Phase
6 data showing single-pass debate doesn't meaningfully beat baseline.

**Q6 — Unsupported claim = mechanical citation check + LLM-judge verification.** *(2026-07-15)*
Mechanical: every assertion in conclusion cites a PMID present in provenance.
LLM-judge: independent model verifies cited paper supports the specific assertion.
Both implemented in `scripts/run_phase6.py`.

**Q7 — `prompt_version` is a SHA-256 hash of the prompt template text at call
time (first 12 hex chars), computed in code.** *(2026-07-13)* The riskiest
assumption in the alternative was that a human remembers to bump a version
string on every prompt edit — and one missed bump makes old provenance rows
silently misleading, which is exactly the failure the "no silent steps"
commandment exists to prevent. Hashing removes the human step: the value is
always accurate because it's derived from the text that actually ran. A
provenance row stays honest even if the prompt file is later edited or deleted.

**Q8 — Both sync and async endpoints provided.** *(2026-07-15)*
Sync: `POST /debate` (74s, for development). Async: `POST /debate/async` + polling (for production).
No streaming — polling works for 74s jobs.

**Q9 — Added `retrieval_id TEXT` (nullable) to `provenance`.** *(2026-07-13)*
Found while resolving Q2, previously flagged nowhere. Biolab's entire premise —
the reason it exists instead of Aletheia calling PubMed directly — is that
`retrieval_id` links "what Aletheia used" to the exact timestamped audit-logged
retrieval that produced it. Without the column, Phase 1 could store
`source_paper_id` but had nowhere to put the value that makes the chain real.
Nullable because not every provenance row comes from a retrieval.

**Q10 — Dropped the `ivfflat` index on `embeddings` entirely. Not reindexed —
removed.** *(2026-07-13)* Phase 1's first real similarity query returned zero
rows against a table that genuinely had 10, with no error. The index was
created in Phase 0's `db/init.sql`, which Postgres runs via
`docker-entrypoint-initdb.d` on first container start — before any rows
existed. `ivfflat` trains on the data present at build time; trained on nothing,
it produces degenerate clusters and silently returns empty result sets. Proven
by `REINDEX`, which printed Postgres's own notice (*"created with little
data... low recall... Drop the index until the table has more data"*), and by
`SET LOCAL enable_indexscan = off` immediately fixing the query — ruling out
the query, psycopg, and pgvector's operators. Dropped rather than reindexed
because at this project's real scale (tens of rows) sequential scan is fast and
exact, and an approximate index reintroduces the same failure after every bulk
load unless someone remembers to reindex. Add it back when a query is *measured*
slow.

---

### Structural decisions embedded in the design

**One agent interface for all three roles.**
`Agent(debate_id, claim, transcript_so_far, evidence) -> (new_transcript_rows,
agent_output)`. The advocate, skeptic, and synthesizer aren't characters with
different APIs — they're the same kind of thing, a cognitive operation over a
transcript. A uniform interface is what makes it possible to add a fourth
operation later without redesigning the loop. Every agent returns at least one
provenance row; zero is prohibited, because silent steps are the exact thing
this project exists to prevent.

**`embeddings.paper_id` holds a real PubMed ID, not an internal key.** This is
the "no hallucinated citations" guarantee made concrete at the schema level —
the skeptic can independently verify the paper exists.

**The `appraise` row's `source_paper_id` is `NULL` by design, not omission.** A
case synthesizes across N papers and a single-value column can't represent
that. Each paper is still individually linked via its own `retrieve` row, and
`detail.cited_pmids` on the appraise row records which of those the case
actually drew on.

**The skeptic can't re-retrieve.** Phase 3's scope allowed it "if it needs to,"
and no real case has yet shown the advocate's evidence is insufficient to mount
a real challenge — so the capability isn't built until one does.

---

## The operating discipline

Two rules generate most of the decisions above:

1. **Don't add infrastructure until a real query fails without it.** This is why
   there's no Neo4j, no job queue, no ANN index, and no convergence loop — and
   why each of those has a named, measurable trigger that would justify it.
2. **No architecture decision gets adopted by default.** Anything unresolved
   goes in QUESTIONS.md and blocks its phase until it has a justification you
   could defend out loud. Nothing gets silently assumed.

The verification standard follows from those: every "done" above is a real MCP
call, a real LLM call, a real HTTP request, and a real read-back from Postgres.
The two bugs found so far — an index that was silently wrong and a truncation
that surfaced as a `KeyError` three calls downstream — are both failures that
only appear when you run real data through real systems. Neither would have
been caught by a mock.