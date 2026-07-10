# Open Questions

> Per STAFF_ENGINEER.md Rule 8/9: no architecture decision gets adopted by
> default. Every entry here blocks a specific phase in [BLUEPRINT.md](BLUEPRINT.md)
> until it has a real answer with a stated justification — not a guess.
>
> Status legend: `OPEN` — unresolved, blocking. `DECIDED` — answered below,
> with the justification you should be able to defend out loud.

---

### Q2 — Biolab MCP tool contract {#q2}

**Status:** OPEN
**Blocks:** Phase 1

DESIGN.md's MCP contract is invented, not verified. What does Biolab's
actual PubMed tool expose — search only, or full-text fetch too? What's the
rate limit? Does it return abstracts or require a second call for full text?
This has to be checked against the real MCP server before any retrieval code
is written, or Phase 1 will be built against a fiction.

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

### Q5 — Debate loop termination {#q5}

**Status:** OPEN
**Blocks:** Phase 2, Phase 3

Who decides the skeptic is done challenging and synthesis should start?
Options:
- Fixed: advocate → skeptic → synthesizer, exactly one pass each, no back-and-forth
- Bounded loop: skeptic can force a re-appraisal from advocate, capped at N rounds
- Convergence check: loop until skeptic raises no new challenge, or cap hits

**Why this matters:** the agent interface contract in DESIGN.md assumes a
fixed pipeline. A bounded or convergence loop changes the interface (agents
need a way to signal "done" vs "here's a new challenge") — this should be
picked before Phase 2's agent contract is written, not retrofitted after.

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

### Q7 — Prompt versioning {#q7}

**Status:** OPEN
**Blocks:** Phase 2

DESIGN.md's provenance schema includes a `prompt_version` column. Is that
enough — a string tag bumped by hand — or does provenance need to store the
actual prompt text/hash inline, so a provenance row is self-contained and
interpretable even if the prompt file is later edited or deleted?

**Riskiest assumption:** a human remembers to bump the version string every
time a prompt changes. If that discipline slips even once, old provenance
rows become silently misleading — which is exactly the failure mode README's
commandment #2 ("no silent steps") is meant to prevent.

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
