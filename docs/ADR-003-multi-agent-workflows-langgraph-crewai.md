# ADR-003: Multi-agent evidence-review and red-team workflows on LangGraph + CrewAI

**Status:** Proposed (needs sign-off on the open questions at the bottom)
**Date:** 2026-10-09
**Supersedes in part:** ADR-001's rating of "LangChain/LangGraph rewrite" as a poor fit, and
BLUEPRINT's "LangChain/LangGraph — not at all" out-of-scope line. See *Honest framing*.

## Context

Phase 6's eval (n=10) found the three-agent debate on a single claim did **not** beat one
well-prompted call, at about 7.4x the cost. The cause is plausible: Advocate and Skeptic are the
same model reading the same evidence, so they largely agree with themselves.

Multi-agent structure earns its cost only when the task has parallel subtasks, roles that need
different tools, or a real adversary. Two problems in Aletheia's domain have those properties:

1. **Systematic literature review (SR).** A real SR is staged and parallel (frame the question,
   search several sources, screen every paper, extract data, appraise bias and contradictions,
   synthesize). Standard practice is *dual independent screening with a third reviewer resolving
   disagreements*, which is a multi-agent protocol with a measurable property (inter-rater
   agreement) and published ground truth (the included-study lists of published reviews).
2. **Red team vs defender.** An attacker generates poisoned evidence; the defender (guardrails plus
   the SR workflow) must survive it. This is a genuine adversary, and it measures the guardrails
   built in Phases 9-10 instead of trusting them.

The audience is students and the author; the goal is to learn guardrails, security, auth, agent
orchestration, and a TypeScript frontend. Both frameworks are wanted in the system.

## Honest framing

This ADR does **not** claim a query failed without these frameworks, which is the README's first
commandment. It claims a learning objective, and it bounds the cost of that objective with gates:

- **Baseline first.** Phase 12 builds the SR workflow in plain Python with no framework. A framework
  stays only if it matches or beats that baseline on the metrics below, or buys a capability the
  baseline cannot have (durable resume, human-approval pause) that is demonstrated, not asserted.
- **Provenance stays ours.** The README rejected LangChain because it "hides agent decisions inside
  abstractions you don't control." That objection is the acceptance test here: every node and every
  crew task must write provenance rows through Aletheia's own helper, with the real prompt hash.
  Framework state is never the source of truth. A framework that cannot meet this is dropped.

## Decision

**LangGraph owns the outer workflow; CrewAI owns bounded role-based collaboration inside a node.**

| Concern | Owner | Why |
|---|---|---|
| Workflow state, fan-out/fan-in, retries | LangGraph | Explicit graph; every transition is inspectable |
| Durable checkpoints, resume after crash | LangGraph (Postgres checkpointer) | To verify in spike |
| Human approval gate (student approves inclusion list) | LangGraph interrupt | To verify in spike |
| Budgets, guardrail nodes, owner checks | LangGraph nodes we write | Must sit *between* every agent step |
| Screening crew: Screener A, Screener B, Adjudicator | CrewAI (inside one graph node) | Role/task shape is natural here |
| Attacker crew: Generator, Mutator | CrewAI (inside one graph node) | Same |
| Every LLM call | `app.llm.call_tool` (ADR-001 gateway) | Provider neutrality, model recorded in artifacts, cost accounting |

New code lives in `app/workflows/` and `app/redteam/`. FastAPI, Postgres state, provenance tables,
the single-call default path, and the existing guardrails are unchanged. This is an additive layer,
not the "rewrite" ADR-001 rejected.

### Workflow 1: systematic review graph

```
frame -> search (parallel per source) -> screen (fan-out, dual + adjudicate)
      -> [human gate: approve inclusion list] -> extract (per paper, parallel)
      -> appraise (bias, contradictions, retractions) -> synthesize (rubric v1, citations validated)
```

### Workflow 2: red-team loop

```
generate attacks -> inject into SANDBOX corpus -> run defender -> score -> mutate survivors -> repeat (budgeted)
```

Safety boundary: attacks are strings fed to Aletheia's own pipeline through a fixture retriever.
Nothing is published to PubMed or any external system; the run uses a synthetic corpus only.

## Guardrails (cross-cutting, required before either workflow ships)

| # | Guardrail | Status |
|---|---|---|
| G1 | Claim/question input validation | Done (Phase 9) |
| G2 | Evidence injection screen at the **shared retrieval boundary** | Exists but only in `single_call`. **Gap:** `/debate/multi-agent` is unscreened. Phase 11 closes it. |
| G3 | **Inter-agent output screening.** One agent's output is untrusted input to the next. A poisoned abstract can make the Advocate or Screener emit instruction-like text that a later agent trusts. | New |
| G4 | Least-privilege tools per agent (screeners get read-only retrieval, no write tools) | New |
| G5 | Hard budgets per run: LLM calls, tokens, USD, wall time. Exceeding stops the run with a partial, flagged result. | New |
| G6 | Citation integrity per agent, not only at the end | Generalize from `single_call` |
| G7 | Auth + ownership on every run, checkpoint and approval (Phase 10). Checkpoints are a new IDOR surface. | Extend |
| G8 | Provenance row for every node and crew task, including framework, node name, prompt hash | New |

## Evaluation (the proof; commandment 4)

**SR.** Pick published systematic reviews whose included-study lists are publicly available (Q11).
Run the workflow on each review's question restricted to papers published before the review's search
date, and compare against the gold included list:
- recall of included studies, precision, and work saved over sampling at 95% recall (WSS@95)
- inter-screener agreement (Cohen's kappa) between Screener A and B
- cost per included study

Baselines: (a) plain-Python version of the same graph, (b) one-shot "list the relevant papers" call,
(c) PubMed keyword ranking alone.

Hypotheses, each with a falsifier:
- **H1** Dual independent screening plus adjudication beats a single screener on recall at equal
  precision. *Falsified if* recall gain is within run-to-run noise (repeat each run, report spread).
- **H2** Cost stays under a per-run cap set after the Phase 12 baseline is measured. *Falsified if*
  the framework versions exceed the plain-Python cost with no measured quality gain.
- **H3** CrewAI screening matches plain-Python screening quality. *If not, CrewAI is demoted to
  optional or removed.*

Known threat to validity: the model may have seen published reviews in training. Mitigation: ground
answers in retrieved papers, prefer recent reviews, and report the one-shot baseline (b) as the
contamination check, since it can only succeed by memorization.

**Red team.** Attack success rate (ASR) per attack class: the fraction of attacks that get past
`screen_evidence` or change a verdict, citation set, or confidence beyond a tolerance. Report ASR
before and after each guardrail, the false-positive rate on benign abstracts (the 714-abstract live
PubMed scan method), and the rate at which mutated attacks evade the regex tripwire. Mutation
survivors become new regression tests.

## Dependency footprint (measured 2026-10-09, `pip install --dry-run` against this project's pins)

| Install | Resolves with project pins | Notable additions |
|---|---|---|
| langgraph | yes | langgraph 1.2.14, langchain-core 1.6.9, checkpoint libs |
| crewai | yes | crewai 1.6.1, **chromadb 1.1.1, onnxruntime 1.31.0** (heavy) |
| both | yes | the union of the above; no conflicts reported |

CrewAI's footprint is the main cost. Containerizing it in a separate optional extra (`poetry
--with workflows`) keeps the core API image small.

## Framework scoring (filled in by the Phase 13-14 spikes, not by opinion)

| Criterion | Plain Python | LangGraph | CrewAI |
|---|---|---|---|
| Exact prompt text visible and hashed in provenance | baseline | spike | spike |
| Guardrail hook between every agent step | baseline | spike | spike |
| Hard budget enforcement | baseline | spike | spike |
| Persist + replay + resume a run | no | spike | spike |
| Human-approval pause | no | spike | spike |
| LLM calls routed through `app.llm.call_tool` | yes | spike | **gate**: must be possible |
| Dependency weight | none | measured above | measured above |
| Cost and quality vs baseline | baseline | spike | spike |

## Options considered

| Option | Verdict |
|---|---|
| Stay on `single_call`, no multi-agent | Safe, but forgoes the stated learning goal |
| Plain-Python multi-agent only | Best baseline; kept as Phase 12, not as the whole answer |
| LangGraph only | Strong fit for orchestration; leaves the role-based crews unexplored |
| CrewAI only | Fast to start; weaker control over state, budgets and prompt text |
| **Plain baseline, then LangGraph outer + CrewAI inner, each behind a gate** | Chosen |

## Consequences

- Positive: a measurable answer to "does multi-agent help", a security story backed by an adversary,
  and an honest framework comparison with numbers.
- Negative: more moving parts, a heavier optional dependency set, and framework API churn to track.
- Risk: using two frameworks adds integration surface. Mitigation: the CrewAI crew is a pure function
  of (inputs -> validated structured output) inside one graph node, so it can be removed without
  changing the graph.

## Open questions (recorded in QUESTIONS.md)

- **Q11** Which published reviews form the gold set, and who verifies each included-study list?
- **Q12** Can CrewAI be routed through `app.llm.call_tool`? If not, it fails the gate.
- **Q13** Checkpoint ownership: how do LangGraph thread ids map to `owner_sub`, and does the Postgres
  checkpointer allow owner-scoped reads, or do we enforce ownership in our own `runs` table?
