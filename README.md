# Aletheia

> *"I designed a system where AI doesn't just answer — it argues with itself, shows its work, and cites its sources. This is how you build scientific AI you can actually trust."*

A multi-agent scientific reasoning system where AI agents with distinct epistemic roles debate a claim before producing a conclusion. Every piece of evidence is traced back to its exact source, version, and retrieval step.

---

## The Problem

A single LLM call collapses five distinct cognitive operations into one opaque text artifact:

1. **Retrieval** — finding relevant evidence
2. **Evidence appraisal** — judging source quality
3. **Uncertainty estimation** — knowing what we don't know
4. **Conflict resolution** — handling contradictory evidence
5. **Synthesis** — producing a conclusion

You cannot audit step 2. You cannot re-run step 4 with different evidence. You cannot know if step 3 happened at all. Aletheia makes each step explicit, observable, and traceable.

---

## Architecture

```
User types a scientific claim
           │
           ▼
        FastAPI
  POST /debate { claim }
  returns { debate_transcript, sources, confidence }
           │
           ▼
    Custom Agent Loop
           │
    ┌──────┴──────┐
    │  ADVOCATE   │ ──► Biolab MCP Server (PubMed retrieval)
    │  builds case│
    └──────┬──────┘
           │ passes evidence + case
    ┌──────┴──────┐
    │   SKEPTIC   │  challenges sources, flags uncertainty,
    │             │  identifies conflicting evidence
    └──────┬──────┘
           │ debate transcript
    ┌──────┴──────┐
    │ SYNTHESIZER │  resolves conflict, assigns confidence,
    │             │  produces structured conclusion
    └──────┬──────┘
           │ writes provenance at every step
           ▼
        pgvector
  ┌─────────────────┐   ┌──────────────────────────┐
  │  embeddings     │   │  provenance              │
  │  paper_id       │   │  claim                   │
  │  embedding      │   │  agent                   │
  │  metadata       │   │  source_paper_id         │
  │  content        │   │  action                  │
  └─────────────────┘   │  timestamp               │
                        └──────────────────────────┘
           │
           ▼
     Eval Harness
  single model baseline vs debate loop
  measures: unsupported claims, citation accuracy,
            confidence calibration
```

---

## Why Every Decision Exists

### Multi-agent loop, not a single model with better prompting
A prompt saying "steelman the opposing view" still collapses all five steps into one opaque forward pass. Agent separation forces each step to produce a traceable artifact. The advocate, skeptic, and synthesizer are not characters — they are the five cognitive operations made explicit.

### Custom agent loop, not LangChain
Provenance tracing is the core product. LangChain hides agent decisions inside abstractions you don't control. A custom loop gives you the exact artifact at every step — which is what you need to write lineage you can query later.

### pgvector, not a standalone vector database
pgvector lives inside Postgres. The provenance table lives next to the embeddings table. One database, two query shapes: semantic search over literature + structured queries over reasoning lineage. No sync problem, no second connection.

### pgvector before Neo4j
Provenance relationships are a graph — claims, agents, sources, contestations. Neo4j will eventually be the right store. But we don't know the query shapes yet. The rule: **don't add infrastructure until a real query fails without it.**

### FastAPI, not a notebook entry point
There is a real frontend user typing a claim and expecting structured data back. A notebook cannot serve a browser. FastAPI is the thinnest layer that can.

### Biolab MCP Server for PubMed retrieval
Grounded retrieval from a real scientific database. No hallucinated citations. Every paper the advocate uses has a real PubMed ID the skeptic can contest.

### Eval harness from day 1
The thesis of Aletheia is that debate reduces unsupported claims vs a single-model baseline. If we don't measure this, we don't know if the system works. The eval notebook is not optional — it is the proof.

---

## Stack

| Layer | Tool | Why |
|---|---|---|
| Frontend | Browser | Real user, real claim |
| Backend | FastAPI | Serves structured debate to browser |
| Agent loop | Custom Python | Full control over provenance artifacts |
| Evidence retrieval | Biolab MCP + PubMed | Grounded, citable sources |
| Vector + provenance store | pgvector | Two query shapes, one database |
| Eval | Jupyter notebook | Hallucination rate vs baseline |
| Future graph store | Neo4j | When provenance queries outgrow pgvector |

---

## 90-Day Deliverable

A minimal 2-agent debate (advocate + skeptic) over 5 curated scientific claims, using Biolab's PubMed MCP tool for retrieval. Provenance written to pgvector. An evaluation notebook comparing hallucination rate to a single-model baseline, showing the debate loop reduces unsupported claims.

---

## The Commandments

1. Don't add infrastructure until a real query fails without it.
2. Every agent decision produces a traceable artifact — no silent steps.
3. Every claim links back to a real source with a real ID.
4. The eval harness is not optional — it is the proof.
5. The agents are not characters. They are cognitive operations made explicit.
