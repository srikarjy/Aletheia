# Biolab MCP Server

[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue)](https://python.org)
[![Go Version](https://img.shields.io/badge/go-1.23%2B-00ADD8)](https://golang.org)
[![MCP](https://img.shields.io/badge/MCP-1.28.1-purple)](https://modelcontextprotocol.io)
[![License](https://img.shields.io/badge/license-MIT-green)](LICENSE)
[![PyPI](https://img.shields.io/pypi/v/biolab-mcp)](https://pypi.org/project/biolab-mcp/)
[![Docker](https://img.shields.io/badge/docker-ghcr.io%2Fsrikarjy%2Fbiolab--mcp-blue)](https://github.com/srikarjy/biolab-mcp/pkgs/container/biolab-mcp)

> *"AI agents querying biological databases leave no audit trail. Six months later, nobody can answer: what exact query returned this result, when, and was that paper peer-reviewed at the time? Biolab solves that."*

A **dual-implementation** (Python + Go) MCP server that sits between AI agents and biological/scientific databases. Every query is intercepted, logged with full retrieval context, and returns a `retrieval_id` that calling systems store alongside their reasoning traces — creating an end-to-end auditable chain from conclusion back to raw source.

## The Problem

A drug discovery team uses an AI agent to research gene targets. The agent queries PubMed 200 times over three days and surfaces a paper claiming gene X is upregulated in pancreatic cancer. A scientist makes a decision based on that. Six months later, during FDA submission:

- What exact query returned that paper?
- What date was it retrieved?
- Was it peer-reviewed at retrieval time, or a preprint published later?
- Did the agent summarize it accurately, or hallucinate details?

Without Biolab, nobody can answer any of those questions. The retrieval is invisible.

## What Biolab Does

Biolab is an **interception and logging layer**, not a retrieval layer. It doesn't interpret evidence, rank it, or summarize it — it records what happened, verbatim, so an agent's claim can always be traced back to an unforgeable original.

```
Aletheia Advocate Agent
    ↓  MCP tool call (e.g. search_pubmed)
Biolab MCP Server
    ↓  HTTP
Source API (PubMed, Europe PMC, ClinicalTrials.gov, bioRxiv/medRxiv)
    ↓  paper
Biolab writes retrieval record to database
    ↓  paper + retrieval_id
Back to Advocate Agent
```

The agent gets the paper it asked for. Biolab gets a permanent, queryable record of exactly what happened.

## Sources Supported

| Source | MCP Tool | CLI Command | Notes |
|--------|----------|-------------|-------|
| **PubMed** | `search_pubmed` | `biolab search` | E-utilities, full XML stored |
| **Europe PMC** | `search_europepmc` | `biolab search-europepmc` | Free, indexes bioRxiv/medRxiv |
| **ClinicalTrials.gov** | `search_clinicaltrials` | `biolab search-clinicaltrials` | API v2, condition-based search |
| **bioRxiv/medRxiv** | `search_biorxiv` | `biolab search-biorxiv` | Date-range pagination (API limit) |

All sources share a **single SQLite audit database** with source-agnostic schema.

## Quick Start

### Python (pipx / pip)
```bash
pipx install biolab-mcp
# or
pip install biolab-mcp
```

### Go (pre-built binary)
```bash
# Download from GitHub Releases
curl -L https://github.com/srikarjy/biolab-mcp/releases/latest/download/biolab_darwin_arm64.tar.gz | tar xz
./biolab search "BRCA1 pancreatic cancer" --max 3
```

### Docker
```bash
docker run -v $(pwd)/data:/data ghcr.io/srikarjy/biolab-mcp:latest
```

### Homebrew (coming soon)
```bash
brew tap srikarjy/tap
brew install biolab
```

## Usage

### CLI (Scientist-Friendly)
```bash
# Search PubMed
biolab search "BRCA1 pancreatic cancer" --max 5

# Search Europe PMC
biolab search-europepmc "BRCA1 pancreatic cancer" --max 5

# Search ClinicalTrials.gov
biolab search-clinicaltrials "pancreatic cancer" --max 5

# List bioRxiv preprints (no free-text search - API limitation)
biolab search-biorxiv neuroscience --max 10
biolab search-biorxiv all --server medrxiv --max 10

# Retrieve full audit record
biolab get <retrieval_id>

# List recent retrievals
biolab list --source pubmed --limit 10

# Export for analysis
biolab export evidence.jsonl --source clinicaltrials

# Run demo
biolab demo --query "BRCA1 pancreatic cancer"
```

### MCP Tools (Agent-Friendly)
```json
// Search any source
{"name": "search_pubmed", "arguments": {"query": "BRCA1 pancreatic cancer", "agent_id": "aletheia:advocate", "max_results": 5}}
{"name": "search_europepmc", "arguments": {"query": "BRCA1 pancreatic cancer", "agent_id": "aletheia:advocate", "max_results": 5}}
{"name": "search_clinicaltrials", "arguments": {"query": "pancreatic cancer", "agent_id": "aletheia:advocate", "max_results": 5}}
{"name": "search_biorxiv", "arguments": {"category": "neuroscience", "agent_id": "aletheia:advocate", "max_results": 5, "server": "biorxiv"}}

// Retrieve full audit record (works for ALL sources)
{"name": "get_retrieval", "arguments": {"retrieval_id": "uuid-from-search"}}
```

### Python API
```python
from biolab.pubmed_client import search_and_fetch
from biolab.retrieval_log import write_retrieval, get_retrieval
from biolab.db import connect

conn = connect("biolab.db")
papers = search_and_fetch("BRCA1 pancreatic cancer", 3)
for p in papers:
    record = write_retrieval(conn, query="...", pmid=p.pmid, ...)
    print(record.retrieval_id)
```

## Audit Trail Schema (v2)

```sql
CREATE TABLE retrievals (
    retrieval_id     TEXT PRIMARY KEY,  -- UUID
    source           TEXT NOT NULL,     -- "pubmed", "europepmc", "clinicaltrials", "biorxiv"
    external_id      TEXT NOT NULL,     -- PMID, NCT ID, DOI, etc.
    query_text       TEXT NOT NULL,     -- exact query sent to source
    retrieved_at     TEXT NOT NULL,     -- ISO 8601 UTC
    agent_id         TEXT NOT NULL,     -- e.g. "aletheia:advocate"
    source_metadata  TEXT NOT NULL,     -- JSON: source-specific fields
    raw_response     TEXT NOT NULL,     -- verbatim XML/JSON from source
    snapshot         TEXT NOT NULL,     -- JSON: structured fields (title, abstract, authors, journal, DOI, pub types, MeSH/conditions)
    response_hash    TEXT NOT NULL      -- SHA-256 of raw_response
);
```

**Key properties:**
- One row per paper retrieval (not per query)
- Raw response stored verbatim — parsing bugs are recoverable
- SHA-256 hash enables future drift/retraction detection
- WAL mode + background write queue for concurrency safety

## Architecture

```
biolab/
├── cli.py              # Typer CLI (search, get, list, export, demo)
├── server.py           # FastMCP server (5 tools)
├── db.py               # SQLite + schema
├── models.py           # RetrievalRecord dataclass
├── retrieval_log.py    # Only writer + background queue
├── pubmed_client.py    # PubMed E-utilities wrapper
├── europepmc/          # Europe PMC adapter
├── clinicaltrials/     # ClinicalTrials.gov adapter
└── biorxiv/            # bioRxiv/medRxiv adapter
```

**Design principles:**
- Python + Go implementations (same interface, different runtimes)
- MCP tools, not REST API — zero integration overhead for agents
- Database, not log files — structured queries across time
- SQLite + WAL, not Postgres — until concurrent writers hit
- Hard-fail, never degrade — paper without `retrieval_id` is worse than error
- Live-API tests, no mocks — real XML/JSON shape catches real bugs

## Development

```bash
# Python
pip install -e .[dev]
pytest tests/ -v

# Go
cd go-biolab
go test ./...
go build -o biolab ./cmd/cli
go build -o biolab-server ./cmd/server
```

## Deployment

| Target | Method |
|--------|--------|
| **Local** | `pipx install biolab-mcp` or download binary |
| **CI/CD** | GitHub Actions → PyPI + GHCR + GitHub Releases |
| **Containers** | `docker pull ghcr.io/srikarjy/biolab-mcp:latest` |
| **Linux packages** | `.deb`, `.rpm`, `.apk` via goreleaser |

## Roadmap

- [ ] Evidence drift detection (retraction monitoring via response hashes)
- [ ] Provenance graph (cross-source linking by DOI)
- [ ] Nextflow/Snakemake plugins
- [ ] Rate limiting + caching (audit-safe)
- [ ] Auth + multi-tenant support

## License

MIT — see [LICENSE](LICENSE)

## Author

**Srikar Jy** — [srikarjy@gmail.com](mailto:srikarjy@gmail.com)