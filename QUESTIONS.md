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

### Q4 — What does "confidence calibration" mean here? {#q4} — SPLIT 2026-07-14

The original question conflated two things that resolve at different phases:
what **rule** produces the synthesizer's confidence number (blocks Phase 4),
and whether that rule's outputs **track truth** (blocks Phase 6). Split so
Phase 4 can proceed without pretending to a statistical validation that one
claim — or five — cannot provide.

#### Q4a — the rule that produces the number — DECIDED 2026-07-14

**Decision:** the synthesizer's confidence is produced by **rule-constrained
judgment against a written rubric** (v1 below), embedded verbatim in the
synthesizer prompt template. The rubric is a fixed set of anchor cases
mapping evidentiary situations to confidence bands. The structured output
(same forced-tool-use pattern as Phases 2/3) must include `confidence`, a
`confidence_rationale` that names the anchor applied and the rows that drove
it, and `driving_provenance_ids` — and **code validates** that every listed
ID exists among *this debate's* provenance rows, rejecting/retrying the call
otherwise. Citation is enforced, not honor-system.

**What this is, stated honestly:** the rubric does not eliminate judgment,
it relocates it — "does this challenge undermine the *central* evidence?" is
still a classification the LLM makes. What the rubric buys is
accountability: the standard is written down in the prompt, so a human can
check any band assignment against it and disagree with a specific anchor,
instead of arguing with a free-floating 0.6. At this phase, `confidence:
0.7` does **not** mean "correct 70% of the time" — it means "band C/D per
rubric v1." Whether the rubric's numbers track truth is exactly Q4b.

**Rubric v1** (to be embedded verbatim in `SYNTHESIZER_PROMPT_TEMPLATE` in
Phase 4 — see versioning note below):

```
CONFIDENCE RUBRIC v1

"confidence" means: the degree to which the claim is supported by the
evidence in this transcript, after the skeptic's challenges are accounted
for. It is NOT a probability that the claim is true in the world.

Step 1 — validity screen. Check each skeptic challenge against the actual
evidence rows. A challenge is VALID only if the specific weakness it names
is present in the cited text. A challenge that miscites, mischaracterizes,
or raises a hypothetical not grounded in the evidence is INVALID — discard
it and say so in confidence_rationale.

Step 2 — place the debate against the anchors, using only VALID challenges:

  A. A valid challenge directly undermines the advocate's central evidence
     (e.g. the key citation does not say what the case claims)
     → confidence ≤ 0.3
  B. The evidence rows genuinely conflict on the central claim and neither
     side is invalidated → confidence 0.4–0.6, verdict "unresolved" — state
     explicitly that the conflict could not be resolved.
  C. Valid challenges exist but touch only peripheral points; the central
     citations hold → confidence 0.5–0.7
  D. No valid substantive challenges and the advocate's citations hold up —
     including the case where every skeptic challenge was INVALID
     → confidence ≥ 0.8

Anchors are cases, not a partition: where bands overlap (0.5–0.6), the
verdict distinguishes them. Values in the gaps (0.3–0.4, 0.7–0.8) are
allowed only by naming the nearest anchor and justifying the offset in
confidence_rationale.

confidence_rationale must name the anchor letter applied and the specific
transcript/provenance rows that drove the placement. driving_provenance_ids
must list only IDs that appear in this debate's provenance.
```

**Versioning:** the rubric lives inside the synthesizer prompt template, so
Q7's `prompt_version` hash covers it automatically — any edit, even one
word of an anchor, produces a new hash on every subsequent provenance row.
The rubric is a measurement instrument: it must be **frozen before Phase 5
starts** and not edited between the 5 claims, or the confidence scores stop
being comparable and Phase 6's table compares readings from two different
thermometers. A mid-eval hash change in provenance is the tripwire.

**Justification:** Phase 4's exit criterion asks for "a confidence score
defined by an explicit rule, not vibes" — it never asked for calibration,
which requires many claims with known outcomes. A written rubric + enforced
citation of driving rows is that explicit rule: checkable and reproducible,
just not yet statistically validated. Anchor D's validity screen exists
because the fixed pipeline (Q5) has no rebuttal turn — without a sanctioned
way to discard an unsound skeptic challenge, the confidence floor would be
set by skeptic aggression rather than evidence quality (Phase 3 proved the
skeptic can be substantive; nothing proves it can't also overreach). Anchor
B exists because Phase 4's requirement explicitly includes "explicitly fails
to resolve" as a legitimate outcome, and Q3 plans at least one claim with no
clean resolution — the rubric must reward an honest "unresolved" over
fabricated confidence. The deterministic alternative (a formula over
transcript features, e.g. counting challenges) was rejected: it would be
gameable, brittle, and would pretend a precision it doesn't have.

#### Q4b — does the rubric's output track truth? {#q4b}

**Status:** OPEN
**Blocks:** Phase 6 (not Phase 4)

What Phase 6 reports about confidence must be directional/ordinal at n=5 —
e.g. "did the known-contested claim receive the lowest confidence" and "did
the synthesizer use anchor B rather than fabricating certainty" — reported
as an acknowledged proxy. **Never** a `confidence_calibration_error` scalar:
at n=5 that number would look rigorous and isn't (Rule 12). The exact
proxy metric definition is decided together with Q3's claim selection, since
the check only means something if the eval set contains a claim known to be
contested.

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

**Measured 2026-07-14 (Phase 4):** one synchronous `POST /debate` took **73.7s**
end to end (advocate MCP retrieval + 3 LLM calls: advocate, skeptic, synthesizer).
It did **not** time out, so per the rule above async stays deferred — but 73s is
a real signal, not a comfortable one. Revisit trigger stays as written: introduce
submit-job + poll only when a real request actually times out (or Phase 5's batch
of 5 makes the sequential wait untenable), not preemptively. Kept OPEN.

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
