# Blueprint

> The 90-day deliverable in README.md is a destination, not a path. This is the path.
> Each phase has an exit criterion you can point at and say "this is done" —
> not a vibe, a fact you can verify.

Rule: no phase starts until the previous phase's exit criterion is met.
No phase's scope grows beyond its stated criterion "while we're in there."
If a phase surfaces a decision that isn't made yet, it goes in
[QUESTIONS.md](QUESTIONS.md) — it does not get silently assumed.

---

## Phase 0 — Foundations

**Problem:** There is no substrate to build agents on top of. Every later phase
needs a database and an HTTP entrypoint to exist first.

**Requirement:** A Postgres+pgvector schema and a FastAPI skeleton that can
round-trip a request, before any agent logic exists.

**Scope:**
- `embeddings` and `provenance` tables migrated (see [DESIGN.md](DESIGN.md#database-schema))
- `POST /debate` returns a hardcoded fixture response — no agents, no retrieval
- Nothing else. No auth, no frontend, no MCP.

**Exit criteria:** `curl -X POST /debate -d '{"claim": "..."}'` returns a
well-formed JSON response matching the contract in DESIGN.md, and the two
tables exist with the right columns in a running Postgres instance.

**Open questions this phase must resolve:** [Q1 — provenance schema keys](QUESTIONS.md#q1)

---

## Phase 1 — Grounded retrieval

**Problem:** Without real retrieval, every later agent is reasoning over
nothing (or over hallucinated evidence). Retrieval has to be grounded before
any agent is allowed to make a claim.

**Requirement:** For one hardcoded claim, call the Biolab MCP server, get
real PubMed papers back, embed them, store them in `embeddings`.

**Scope:**
- MCP client wired to Biolab's PubMed tool
- One retrieval call, one claim, no agent loop yet
- Retrieved papers embedded and persisted

**Exit criteria:** Given one fixed claim, the system returns real PubMed IDs
with real titles/abstracts, and rows exist in `embeddings` you can query back
by similarity.

**Open questions this phase must resolve:** [Q2 — MCP tool contract](QUESTIONS.md#q2)

**Status 2026-07-13 — DONE, verified for real.** `scripts/run_phase1.py` (run with
`poetry run python scripts/run_phase1.py`) does exactly the exit criteria: real MCP
call to Biolab returns 5 real PMIDs/titles/abstracts for the hardcoded claim "BRCA1
mutations increase pancreatic cancer risk"; each is embedded (OpenAI
`text-embedding-3-small`) and persisted to `embeddings`; a real cosine-similarity
query against that table returns the correct closest match. Provenance rows also
written with `retrieval_id` (Q9 migration) alongside `source_paper_id`, closing the
audit-trail link Biolab's whole premise depends on.

Found and fixed one real bug along the way: the `ivfflat` index on `embeddings`
(added in Phase 0, before any data existed) trained on zero rows and silently
returned 0 results on similarity queries even after data was inserted — no error,
just wrong. Confirmed via Postgres's own `REINDEX` notice ("ivfflat index created
with little data... low recall... Drop the index until the table has more data").
Dropped the index entirely rather than just reindexing — at this project's actual
scale (5-claim eval set), sequential scan is fast and exact; an approximate index is
premature optimization until a real query is measured to be slow. See `db/init.sql`
and QUESTIONS.md.

---

## Phase 2 — Advocate agent

**Problem:** Retrieval alone is not reasoning. Something has to turn evidence
into a case, and that step has to be traceable — this is cognitive operation
#1 (retrieval) plus #2 (evidence appraisal) made explicit, per README.

**Requirement:** A single agent that takes a claim + retrieved evidence,
produces a structured "case," and writes a provenance row for every action it
takes (not just the final output).

**Scope:**
- Advocate agent only — no skeptic, no synthesizer
- Provenance write on every retrieval/appraisal action, not just the summary

**Exit criteria:** For 1 claim, you can query `provenance` and reconstruct
every step the advocate took, in order, each linked to a real `source_paper_id`.

**Open questions this phase must resolve:** [Q5 — agent loop termination](QUESTIONS.md#q5), [Q7 — prompt versioning](QUESTIONS.md#q7)

**Status 2026-07-13 — DONE, verified for real.** `scripts/run_phase2.py` proves the
exit criteria: for the claim "BRCA1 mutations increase pancreatic cancer risk",
`app/agents/advocate.py` retrieves real evidence via Biolab, writes one "retrieve"
provenance row per paper (each with a real `source_paper_id` + `retrieval_id`), then
calls Claude (`claude-sonnet-4-5`, forced tool-use for structured output) to build an
evidence-based case, writing one "appraise" row with a real `prompt_version` hash
(Q7). The case itself is genuinely grounded — it cited 4 of the 5 retrieved papers
with direct quotes, and correctly did not cite the 5th (an ATM founder-variant paper
retrieved by the query but not actually about BRCA1), matching the "don't overstate
weak evidence" instruction in the prompt.

One design call made without a pre-existing question to resolve it against: the
"appraise" row's `source_paper_id` is `NULL`, by design, not omission — a case
synthesizes across N papers, and a single-value column can't represent that. Each
paper is still linked to a real source individually via its own "retrieve" row;
`detail.cited_pmids` on the appraise row records which of those the case actually
drew on. See `app/agents/advocate.py`'s module docstring for the full reasoning.

Q5 was decided as fixed pipeline (see QUESTIONS.md#q5) — Phase 2 makes exactly one
advocate call, no looping, consistent with that decision.

---

## Phase 3 — Skeptic agent

**Problem:** An advocate alone is a single opinion with extra steps. The
thesis of Aletheia is that a second, adversarial pass surfaces unsupported
claims the advocate's case would otherwise hide.

**Requirement:** A second agent that receives the advocate's case + evidence,
challenges weak sources, flags uncertainty, and identifies conflicting
evidence — with its own provenance trail.

**Scope:**
- Skeptic reads advocate's output; does not re-retrieve from scratch unless it needs to contest with new evidence
- Debate transcript = advocate trace + skeptic trace, ordered

**Exit criteria:** For 1 claim, the debate transcript shows at least one
concrete challenge the skeptic raised against the advocate's case, with a
provenance row proving it happened.

**Open questions this phase must resolve:** [Q5 — agent loop termination](QUESTIONS.md#q5)

**Status 2026-07-13 — DONE, verified for real.** `scripts/run_phase3.py` proves the
exit criteria well past the minimum bar: the skeptic raised 5 concrete challenges
(each its own "critique" provenance row) plus one "assess" row, all against the same
claim used in Phase 1/2. Genuinely substantive, not scripted — it caught the advocate
conflating BRCA1 with BRCA2's higher risk figures, caught a citation (PMID 42274517)
that discusses treatment but doesn't actually establish germline BRCA1 pancreatic
cancer susceptibility, and correctly flagged an irrelevant retrieved paper (ATM
founder variant, no BRCA1 relevance).

Scoped minimally per this phase's own allowance ("does not re-retrieve... unless it
needs to") — the skeptic works from the same evidence the advocate already retrieved,
no new-retrieval capability. No real case yet demonstrates existing evidence is
insufficient to mount a real challenge, so that capability isn't built until one does.

**Real bug found and fixed:** the skeptic's first live run threw `KeyError:
'uncertainty_notes'` — Claude's tool_use response was truncated by `max_tokens=1024`
before finishing the JSON, and a tool schema's `required` fields are a strong hint to
Claude, not an enforced guarantee. Fixed two ways: raised `max_tokens` to 2048 for
real-sized evidence blocks, and added `app/llm.py`'s `call_tool()` helper, which
checks `stop_reason` and raises a clear error at the truncation site instead of
letting a confusing `KeyError` surface several calls downstream. Now shared by both
the advocate and skeptic, and will be reused by Phase 4's synthesizer.

---

## Phase 4 — Synthesizer agent

**Problem:** A debate that never resolves is not a product — someone has to
turn a contested transcript into a structured conclusion with an honest
confidence value.

**Requirement:** A third agent that reads the full transcript, resolves (or
explicitly fails to resolve) the conflict, and emits a structured conclusion
+ confidence score.

**Scope:**
- Synthesizer only reads the transcript; does not retrieve new evidence
- Confidence score must be defined by an explicit rule, not vibes (see Q4)

**Exit criteria:** For 1 claim, `POST /debate` returns a structured
conclusion + confidence score + full transcript + provenance, end to end,
through the real FastAPI endpoint (not a fixture).

**Open questions this phase must resolve:** [Q4 — confidence calibration definition](QUESTIONS.md#q4)

---

## Phase 5 — Scale to the 5-claim eval set

**Problem:** One claim proves the pipeline runs. It proves nothing about
whether the pipeline is *right* — that needs a curated, adversarial set of
claims chosen to actually stress conflicting evidence.

**Requirement:** Select 5 curated scientific claims (with a stated selection
rationale — see Q3) and run the full pipeline over all 5 without code changes
between runs.

**Exit criteria:** All 5 claims produce a debate transcript + conclusion +
provenance, saved and inspectable, with zero manual intervention between
claims.

**Open questions this phase must resolve:** [Q3 — claim selection criteria](QUESTIONS.md#q3)

---

## Phase 6 — Eval harness (the proof)

**Problem:** Per the README commandment — the eval harness is not optional,
it is the proof. Without it, "debate reduces hallucination" is a hypothesis,
not a finding.

**Requirement:** A single-model baseline (same 5 claims, no debate) and a
debate-loop run, compared on: unsupported-claim rate, citation accuracy,
confidence calibration.

**Scope:**
- Baseline notebook: one LLM call per claim, same retrieval context, no agent roles
- Debate notebook: output of Phase 5
- Comparison table/plot across the 3 metrics

**Exit criteria:** A notebook that states, with a number, whether the debate
loop reduced unsupported claims vs baseline — and reports the result honestly
even if the answer is "no" or "inconclusive at n=5."

**Open questions this phase must resolve:** [Q6 — unsupported-claim metric definition](QUESTIONS.md#q6), [Q4 — confidence calibration definition](QUESTIONS.md#q4)

---

## What is explicitly out of scope until a phase above fails without it

Per the README commandment: *don't add infrastructure until a real query
fails without it.*

- Neo4j — not until a provenance query pgvector can't express shows up
- LangChain/LangGraph — not at all, per README's existing justification
- Auth, multi-user, frontend polish — not part of the 90-day deliverable
- Streaming responses from `/debate` — only if synchronous latency proves unusable (see Q8)
