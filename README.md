# Aletheia

> *"I designed a system where AI doesn't just answer — it argues with itself, shows its work, and cites its sources."*

A multi-agent scientific reasoning system where AI agents with distinct epistemic roles debate a claim before producing a conclusion. Every piece of evidence is traced back to its exact source, version, and retrieval step.

**This is a research prototype, not a medical or clinical decision-making tool.** Outputs are LLM-generated reasoning over retrieved abstracts and are not validated for accuracy — see [Results & Limitations](#results--limitations) below before drawing any conclusion from its output about an actual health claim.

---

## Status (as of 2026-07-15)

**Phases 0–6 of 7 are done, each verified against real data, real APIs, and a real database.**

| Phase | What it delivers | Status |
|---|---|---|
| 0 | Postgres+pgvector schema, FastAPI skeleton, fixture `/debate` | ✅ Done 2026-07-10 |
| 1 | Grounded retrieval via Biolab MCP, real embeddings, persistence | ✅ Done 2026-07-13 |
| 2 | Advocate agent, provenance on every action | ✅ Done 2026-07-13 |
| 3 | Skeptic agent, real challenges against real evidence | ✅ Done 2026-07-13 |
| 4 | Synthesizer, rubric-anchored confidence, real `/debate` endpoint | ✅ Done 2026-07-14 |
| 5 | Scale to a curated eval set with zero manual intervention | ✅ Done 2026-07-15 (expanded to 10 externally-cited claims 2026-08-10) |
| 6 | Eval harness: debate vs single-model baseline, with numbers | ✅ Harness built, real run **inconclusive** — [see Results](#results--limitations) |

**New: Interactive React frontend, async job queue, batch processing, caching.**

---

## Default reasoning path (updated 2026-08-11)

`POST /debate` now runs **single_call** — real grounded retrieval followed by one rubric-anchored Claude call — not the three-agent Advocate→Skeptic→Synthesizer pipeline described below. This isn't a walk-back of the multi-agent idea; it's the project's own Phase 6 finding, acted on: the eval harness measured debate against a single well-prompted call and the result was **inconclusive** (see [Results & Limitations](#results--limitations)). Defaulting to three sequential LLM calls with no measured benefit over one isn't defensible on latency or cost grounds, so it stopped being the default.

The debate pipeline is not deleted. It's still real, still tested, and still reachable at `POST /debate/multi-agent` and via `/batch/eval/run` — because it's the eval harness's subject, and the comparison only means something if it keeps running under the same conditions it was measured under. What single_call kept from it, because these earned their keep independent of the three-agent structure: grounded retrieval with a provenance row per paper, rubric-anchored confidence (the same rubric v1, unchanged), and code-enforced citation integrity (a hallucinated or out-of-evidence citation is rejected and retried once, then fails loudly rather than getting silently accepted). See `app/agents/single_call.py`'s module docstring for the full reasoning.

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
   POST /debate { claim }              (default: single_call)
   POST /debate/multi-agent { claim }  (explicit: the pipeline below)
   returns { debate_transcript, sources, confidence }
            │
            ▼
   single_call (default)                  Custom Agent Loop (/debate/multi-agent)
            │                                        │
   ┌────────┴────────┐                       ┌──────┴──────┐
   │ retrieve + one   │──► Biolab MCP Server  │  ADVOCATE   │ ──► Biolab MCP Server
   │ rubric-anchored  │    (PubMed retrieval) │  builds case│     (PubMed retrieval)
   │ Claude call      │                       └──────┬──────┘
   └────────┬────────┘                               │ passes evidence + case
            │                                 ┌──────┴──────┐
            │                                 │   SKEPTIC   │  challenges sources,
            │                                 │             │  identifies conflicts
            │                                 └──────┬──────┘
            │                                        │ debate transcript
            │                                 ┌──────┴──────┐
            │                                 │ SYNTHESIZER │  resolves conflict,
            │                                 │             │  assigns confidence
            │                                 └──────┬──────┘
            │ writes provenance at every step         │ writes provenance at every step
            ▼                                        ▼
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

### Multi-agent loop, not a single model with better prompting — status: not confirmed
This was the original thesis, and the argument still holds in principle: agent separation forces each step to produce a traceable artifact, rather than collapsing five cognitive operations into one opaque forward pass. But it's a claim that has to earn itself against measurement, not just argument, and Phase 6's real eval (n=10, real Claude calls, real PubMed retrieval) found debate did not measurably outperform a single well-prompted call. That's why `/debate` defaults to single_call now (see [Default reasoning path](#default-reasoning-path-updated-2026-08-11)) rather than this pipeline. The debate pipeline stays, at `/debate/multi-agent`, as the eval harness's subject — the question this section poses is still open, not answered no, and the harness is how it gets re-tested rather than re-argued.

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
The thesis of Aletheia is that debate reduces unsupported claims vs a single-model baseline. If we don't measure this, we don't know if the system works. The eval harness is not optional — it is the proof.

---

## Results & Limitations

**Most recent real run (n=10):** the eval harness (`scripts/run_phase6.py`) was run end-to-end against real Claude Sonnet 4.5 calls and real PubMed retrieval via Biolab MCP, across all 10 externally-cited claims.

| Metric | Baseline (single-shot) | Debate (advocate→skeptic→synthesizer) | Delta |
|---|---|---|---|
| Citation accuracy (LLM-judge) | 0.86 | 0.42 | **−0.45** |
| Mechanical unsupported-claim rate | 0% | 10% | **+10pp, debate worse** |
| Verdict matched expected label | — | 4 / 10 | — |
| Cost per claim (real, measured) | $0.014 avg | $0.106 avg | **debate costs 7.4x baseline** |

**At n=10, the debate architecture underperformed the single-model baseline on every metric measured, at roughly 7x the cost.** This is a stronger, more decisive negative result than an earlier n=5 partial run suggested (that run showed a smaller citation-accuracy gap and no signal on unsupported claims — both reversed and widened once the full claim set ran). The eval harness exists to answer this question honestly, including when the answer gets *more* unfavorable as the sample grows, not just when it's inconclusive.

**Reading this result — what it does and doesn't show:**
- **The 10 `expected_verdict` labels are now externally cited** (real Cochrane/systematic-review DOIs or PMIDs — see the table below and `app/claims.py`), not self-graded, so the ground truth here is independently checkable. This wasn't just a formality: sourcing the citations caught two mislabeled verdicts in the original 5-claim set before this run.
- **n=10 is still a pilot for a debate-architecture claim**, though it's now enough to see a consistent, cost-quantified direction rather than a coin-flip-sized signal. A claim like "debate improves citation accuracy" would need a larger, ideally pre-registered eval to generalize from; "debate cost 7.4x more and scored lower on every measured metric in this n=10 run" is what's actually supported.
- **Retrieval is still abstract-only.** Neither pipeline sees full text, structured effect sizes, or study-design metadata (RCT vs. cohort vs. case series) as anything other than free text inside the abstract — a materially weaker evidence base than a real systematic review would use.
- **Confidence scores are still LLM self-reported against a written rubric, not calibrated** against outcomes (no Brier score, no calibration curve — the module docstring already flags this as an open item, gated on having enough claims per confidence bin).
- **One real bug surfaced by this run**: `aspirin_primary_prevention`'s debate arm tripped the mechanical unsupported-claim check (the only such case in either arm) — worth investigating before trusting that specific transcript's citations.

**What this project actually demonstrates:** a working multi-agent architecture with real provenance tracking, a citation-integrity constraint that mechanically rejects unvalidated citations before they reach a user, and an eval harness that measured its own central thesis against externally-cited ground truth and reported a clear, unfavorable, cost-quantified result rather than a hedge. It does not currently demonstrate that debate improves evidence synthesis over a single well-prompted model — at n=10 it demonstrates the opposite, and that's the number to lead with, not around.

**What this project actually demonstrates:** a working multi-agent architecture with real provenance tracking, a citation-integrity constraint that mechanically rejects unvalidated citations before they reach a user, and an eval harness that measures its own central thesis and reports the result even when unfavorable — now against an externally-verifiable ground truth instead of a self-graded one. It does not currently demonstrate that debate improves evidence synthesis over a single well-prompted model — that remains an open, disconfirmed-so-far question pending a full run against the expanded eval set.

---

## Stack

| Layer | Tool | Why |
|---|---|---|
| Frontend | React + Vite + TypeScript | Interactive web interface for real users |
| Backend | FastAPI | Serves structured debate to browser, async job queue |
| Agent loop | Custom Python | Full control over provenance artifacts |
| Evidence retrieval | Biolab MCP + PubMed | Grounded, citable sources |
| Vector + provenance store | pgvector | Two query shapes, one database |
| Eval | Python scripts + JSON | Hallucination rate vs baseline |
| Future graph store | Neo4j | When provenance queries outgrow pgvector |
| Containerization | Docker + docker-compose | Reproducible deployment |

---

## Features

### Core Pipeline
- **Advocate Agent**: Retrieves real PubMed papers via Biolab MCP, builds evidence-based case with full provenance
- **Skeptic Agent**: Challenges advocate's case with concrete, evidence-based critiques (5+ challenges typical)
- **Synthesizer Agent**: Resolves debate using written rubric v1, produces confidence score with code-validated citations
- **Full Provenance**: Every agent action logged to `provenance` table with `debate_id`, `prompt_version`, `retrieval_id`

### Scaling & Production Features
- **Async Job Queue**: `/debate/async` submits job, poll `/debate/jobs/{job_id}` for result
- **Response Caching**: Repeated claims return cached results instantly with new `debate_id`
- **Batch Processing**: `/batch/debate` processes multiple claims sequentially
- **Evaluation Runner**: `/batch/eval/run` executes the full curated eval set
- **Health & Cache Stats**: `/health`, `/cache/stats`, `/cache/clear`

### Interactive Frontend (React + Vite)
- Real-time debate visualization with provenance trace
- Collapsible transcript, sources, and raw JSON
- Confidence bar with verdict badge
- Example claims pre-loaded
- Copy-to-clipboard for sharing results

---

## Local Development

### Prerequisites
- Docker + docker-compose
- Python 3.12 + Poetry
- Node.js 20+ (for frontend dev)
- `.env` file with `OPENAI_API_KEY`, `ANTHROPIC_API_KEY`
- **Biolab MCP Server** — a separate, private PubMed-retrieval MCP server checked out as a sibling directory. It is not part of this repo and isn't published, so real retrieval won't work out of the box for anyone cloning Aletheia on its own. Set `MOCK_RETRIEVAL=true` to run without it (returns a small fixed set of mock papers instead of live PubMed results).

### Quick Start (Docker)
```bash
# Start database and API
docker compose up -d

# API available at http://localhost:8000
# Frontend available at http://localhost:3000 (after building)
```

### Manual Development
```bash
# 1. Start Postgres+pgvector
docker compose up -d db

# 2. Install Python deps
poetry install

# 3. Run API with hot reload
poetry run uvicorn app.main:app --reload --port 8000

# 4. In another terminal, run frontend dev server
cd frontend && npm install && npm run dev
```

### Environment Variables
```bash
# Required
OPENAI_API_KEY=sk-...
ANTHROPIC_API_KEY=sk-ant-...

# Biolab (sibling directory) — see note above; not published, so most people
# cloning this repo should use MOCK_RETRIEVAL=true instead.
BIOLAB_PROJECT_PATH=../Biolab MCP Server
BIOLAB_DB_PATH=../Biolab MCP Server/biolab.db

# Database (default matches docker-compose)
DATABASE_URL=postgresql://aletheia:aletheia@localhost:55432/aletheia

# Mock modes — run without live external dependencies
MOCK_RETRIEVAL=true     # skip Biolab MCP, use a small fixed set of mock papers
MOCK_EMBEDDINGS=true    # skip OpenAI, use deterministic fake embeddings
MOCK_LLM=true           # skip Anthropic, use a canned response per tool name
```

---

## API Endpoints

### Synchronous Debate
```bash
POST /debate
{"claim": "BRCA1 mutations increase pancreatic cancer risk"}

# Response: DebateResponse with verdict, confidence, transcript, sources
```

### Asynchronous Debate (Production)
```bash
POST /debate/async
{"claim": "...", "async_mode": true}

# Returns: { job_id, status: "pending" }
GET /debate/jobs/{job_id}

# Poll until status: "completed" → returns full DebateResponse
```

### Batch Processing
```bash
POST /batch/debate
{"claims": ["claim1", "claim2"], "async_mode": true}

GET /batch/debate/{batch_id}
```

### Evaluation
```bash
POST /batch/eval/run
# Runs all 5 curated claims

GET /batch/eval/claims
# Lists the curated claims with metadata
```

### Utilities
```bash
GET /health                    # Health check + cache stats
GET /cache/stats               # Cache statistics
POST /cache/clear              # Clear response cache
GET /debate/jobs               # List recent jobs
DELETE /debate/jobs/{job_id}   # Delete job
```

---

## Evaluation Claims

Each claim's `expected_verdict` is graded against a specific, cited systematic review or meta-analysis (real DOI/PMID — see `source_citation` in `app/claims.py`), not against this project's own judgment.

| ID | Claim | Category | Expected | Graded against |
|---|---|---|---|---|
| `brca1_pancreatic` | BRCA1 mutations increase pancreatic cancer risk | Conflicting | Unresolved | Yin et al. 2024, PMID 38809921 |
| `vitamin_d_covid` | Vitamin D supplementation prevents severe COVID-19 | Conflicting | Unresolved | Stroehlein et al. 2021 (Cochrane), PMID 34029377 |
| `aspirin_primary_prevention` | Low-dose aspirin reduces all-cause mortality in healthy older adults | Ground Truth | Refuted | Guirguis-Blake et al. 2016 (USPSTF), PMID 27064410 |
| `omega3_cardiovascular` | Omega-3 supplementation reduces major adverse cardiovascular events | Conflicting | Unresolved | Abdelhamid et al. 2020 (Cochrane CD003177.pub5) |
| `hormone_replacement_therapy` | Menopausal hormone therapy reduces all-cause mortality in women under 60 | Conflicting | Supported | Boardman et al. 2015 (Cochrane CD002229.pub4) |
| `vitamin_c_common_cold` | Vitamin C supplementation prevents the common cold | Ground Truth | Refuted | Hemilä & Chalker 2013 (Cochrane CD000980.pub4) |
| `antioxidant_supplements_mortality` | Antioxidant supplements reduce all-cause mortality | Ground Truth | Refuted | Bjelakovic et al. 2012 (Cochrane CD007176.pub2) |
| `glucosamine_osteoarthritis` | Glucosamine reduces pain in osteoarthritis | Conflicting | Unresolved | Towheed et al. 2005 (Cochrane CD002946) |
| `probiotics_pediatric_aad` | Probiotics prevent antibiotic-associated diarrhea in children | Ground Truth | Supported | Guo, Goldenberg et al. 2019 (Cochrane CD004827.pub5) |
| `statins_primary_prevention` | Statins reduce all-cause mortality in primary prevention of CVD | Ground Truth | Supported | Taylor et al. 2013 (Cochrane CD004816.pub5) |

Run eval:
```bash
PYTHONPATH=. poetry run python scripts/run_phase5.py
PYTHONPATH=. poetry run python scripts/run_phase6.py
```

---

## Project Structure

```
Aletheia/
├── app/
│   ├── agents/          # Advocate, Skeptic, Synthesizer
│   ├── batch.py         # Batch processing endpoints
│   ├── claims.py        # 5 curated evaluation claims
│   ├── db.py            # Database connection
│   ├── embeddings.py    # OpenAI embeddings
│   ├── llm.py           # Forced-tool-use helper
│   ├── main.py          # FastAPI app + endpoints
│   ├── mcp_client.py    # Biolab MCP client
│   ├── prompts.py       # Prompt templates + hashing
│   ├── schemas.py       # Pydantic models
│   └── __init__.py
├── db/
│   └── init.sql         # Schema migrations
├── frontend/
│   ├── src/
│   │   ├── App.tsx      # Main React app
│   │   ├── main.tsx     # Entry point
│   │   └── index.css    # Styles
│   ├── index.html
│   ├── package.json
│   ├── vite.config.ts
│   ├── Dockerfile
│   └── nginx.conf
├── scripts/
│   ├── run_phase1.py    # Retrieval verification
│   ├── run_phase2.py    # Advocate verification
│   ├── run_phase3.py    # Skeptic verification
│   ├── run_phase4.py    # Full pipeline verification
│   ├── run_phase5.py    # curated eval set — full debate run
│   └── run_phase6.py    # Baseline vs debate comparison
├── docker-compose.yml
├── Dockerfile
├── pyproject.toml
├── poetry.lock
├── README.md
├── BLUEPRINT.md
├── DESIGN.md
├── QUESTIONS.md
├── PROJECT_STATUS.md
└── STAFF_ENGINEER.md
```

---

## Key Technical Decisions (from QUESTIONS.md)

- **Q1**: `provenance` uses explicit `debate_id UUID` (not composite key) — enables re-running same claim
- **Q2**: Biolab MCP contract verified against real server, not inferred
- **Q3**: 5 claims selected for conflicting evidence + ground truth mix
- **Q4a**: Confidence from written rubric v1, code-validated `driving_provenance_ids`
- **Q4b**: Calibration tested at n=5 via ordinal proxy (directional only)
- **Q5**: Fixed pipeline (advocate→skeptic→synthesizer), no convergence loop
- **Q6**: Unsupported claim = mechanical citation check + LLM-judge verification
- **Q7**: `prompt_version` = SHA-256 hash of template (auto-computed, tamper-proof)
- **Q8**: Sync endpoint (74s measured), async available, streaming deferred
- **Q9**: Added `retrieval_id` to provenance for Biolab audit chain
- **Q10**: Dropped `ivfflat` index — built empty, silently broken; seq scan is exact at this scale

---

## The Commandments

1. **Don't add infrastructure until a real query fails without it.**
2. **Every agent decision produces a traceable artifact — no silent steps.**
3. **Every claim links back to a real source with a real ID.**
4. **The eval harness is not optional — it is the proof.**
5. **The agents are not characters. They are cognitive operations made explicit.**

---

## License

MIT — Built as a portfolio piece demonstrating production-grade AI system design.