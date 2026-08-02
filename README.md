# Aletheia

> *"I designed a system where AI doesn't just answer — it argues with itself, shows its work, and cites its sources. This is how you build scientific AI you can actually trust."*

A multi-agent scientific reasoning system where AI agents with distinct epistemic roles debate a claim before producing a conclusion. Every piece of evidence is traced back to its exact source, version, and retrieval step.

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
| 5 | Scale to 5-claim eval set with zero manual intervention | ✅ Done 2026-07-15 |
| 6 | Eval harness: debate vs single-model baseline, with numbers | ✅ Done 2026-07-15 |

**New: Interactive React frontend, async job queue, batch processing, caching.**

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
The thesis of Aletheia is that debate reduces unsupported claims vs a single-model baseline. If we don't measure this, we don't know if the system works. The eval harness is not optional — it is the proof.

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
- **Evaluation Runner**: `/batch/eval/run` executes full 5-claim eval set
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
- Biolab MCP Server checked out as sibling directory

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

# Biolab (sibling directory)
BIOLAB_PROJECT_PATH=../Biolab MCP Server
BIOLAB_DB_PATH=../Biolab MCP Server/biolab.db

# Database (default matches docker-compose)
DATABASE_URL=postgresql://aletheia:aletheia@localhost:55432/aletheia
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
# Lists the 5 claims with metadata
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

## Evaluation Claims (Phase 5)

| ID | Claim | Category | Expected |
|---|---|---|---|
| `brca1_pancreatic` | BRCA1 mutations increase pancreatic cancer risk | Conflicting | Unresolved |
| `vitamin_d_covid` | Vitamin D supplementation prevents severe COVID-19 | Conflicting | Refuted |
| `aspirin_primary` | Low-dose aspirin reduces all-cause mortality in healthy older adults | Ground Truth | Refuted |
| `omega3_cvd` | Omega-3 supplementation reduces major adverse cardiovascular events | Conflicting | Unresolved |
| `hrt_mortality` | Menopausal hormone therapy reduces all-cause mortality in women under 60 | Ground Truth | Supported |

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
│   ├── run_phase5.py    # 5-claim evaluation
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