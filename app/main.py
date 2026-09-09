"""POST /debate's default reasoning path is single_call (app/agents/single_call.py),
not the three-agent Advocate->Skeptic->Synthesizer pipeline: run_phase6.py's real eval
(n=10, real Claude calls, real PubMed retrieval) found debate underperformed a single
well-prompted call on every metric measured, at 7.4x the cost — see README.md's
Results & Limitations. The debate pipeline is not deleted: it's the eval harness's
subject, and it stays reachable at POST /debate/multi-agent, unchanged, so the
comparison it's measured against keeps meaning something.

Both paths support sync and async modes, and both build the response by
reconstructing it from the provenance rows the agent(s) wrote, so the transcript the
caller sees is literally the audit trail, not a parallel summary that could drift
from it.
"""

import hashlib
import os
import time
from contextlib import asynccontextmanager
from uuid import uuid4

from fastapi import FastAPI, HTTPException, BackgroundTasks, Query, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from app.agents.advocate import advocate
from app.agents.skeptic import skeptic
from app.agents.synthesizer import synthesizer
from app.agents.single_call import single_call
from app.db import connect
from app.embeddings import clear_embedding_cache, get_embedding_cache_stats
from app.infrastructure import RuntimeState, TTLCache
from app.logging import configure_logging, get_logger, request_id_middleware
from app.llm import get_runtime_config
from app.schemas import DebateRequest, DebateResponse, Source, TranscriptEntry

runtime_state = RuntimeState()
# Kept as named module-level stores for backwards-compatible imports in the eval
# harness and tests. They are now bounded TTL caches rather than unbounded dicts.
job_store = runtime_state.jobs
claim_cache: TTLCache[str, DebateResponse] = TTLCache(
    int(os.environ.get("RESPONSE_CACHE_MAX_SIZE", "512")),
    int(os.environ.get("RESPONSE_CACHE_TTL_SECONDS", "21600")),
)


def get_claim_hash(claim: str) -> str:
    """Generate deterministic hash for a claim for caching."""
    return hashlib.sha256(claim.strip().lower().encode()).hexdigest()[:16]


def cleanup_job_store() -> int:
    """Prune expired L1 jobs; the durable ledger remains queryable in Postgres."""
    before = len(job_store)
    # TTLCache prunes on length access.
    after = len(job_store)
    return max(0, before - after)


def _cache_get(claim_hash: str) -> DebateResponse | None:
    try:
        return claim_cache[claim_hash]
    except KeyError:
        payload = runtime_state.get_response(claim_hash)
        if payload is None:
            return None
        result = DebateResponse(**payload)
        claim_cache[claim_hash] = result
        return result


def _cache_put(claim_hash: str, result: DebateResponse) -> None:
    claim_cache[claim_hash] = result
    runtime_state.put_response(claim_hash, result.model_dump(mode="json"))


def _remember(result: DebateResponse, pipeline: str, from_cache: bool = False) -> None:
    runtime_state.remember(result.model_dump(mode="json"), pipeline, from_cache)


async def run_synthesis_pipeline(claim: str, debate_id: str) -> DebateResponse:
    """Default reasoning path: single_call retrieves evidence and resolves the
    claim in one Claude call. See app/agents/single_call.py's module
    docstring for why this replaced the three-agent pipeline as the default."""
    from uuid import UUID
    conn = connect()
    try:
        result = await single_call(conn, claim, UUID(debate_id))

        with conn.cursor() as cur:
            cur.execute(
                "SELECT agent, action, source_paper_id, detail "
                "FROM provenance WHERE debate_id = %s ORDER BY id",
                (debate_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    transcript = [
        TranscriptEntry(
            agent=agent,
            action=action,
            detail=detail if detail is not None else {},
            source_paper_id=source_paper_id,
        )
        for agent, action, source_paper_id, detail in rows
    ]

    sources = [
        Source(
            paper_id=p["pmid"],
            title=p["title"],
            used_by=["single_call"],
            retracted=bool(p.get("retracted")),
            concern=bool(p.get("concern")),
            retraction_notice=p.get("retraction_notice"),
        )
        for p in result["papers"]
    ] + [
        # Trial records are sources too — paper_id carries the NCT id, which
        # frontends can distinguish by its NCT prefix.
        Source(paper_id=t["nct_id"], title=t["title"], used_by=["single_call"])
        for t in result.get("trials", [])
    ]

    return DebateResponse(
        debate_id=debate_id,
        claim=claim,
        conclusion=result["conclusion"],
        verdict=result["verdict"],
        confidence=result["confidence"],
        confidence_rationale=result["confidence_rationale"],
        signal_breakdown=result["signal_breakdown"],
        driving_provenance_ids=result["driving_provenance_ids"],
        transcript=transcript,
        sources=sources,
    )


async def run_debate_pipeline(claim: str, debate_id: str) -> DebateResponse:
    """Multi-agent Advocate->Skeptic->Synthesizer pipeline. Kept unchanged as
    the eval harness's subject (run_phase6.py compares this against
    run_synthesis_pipeline's baseline) — not the default path, see
    POST /debate/multi-agent."""
    from uuid import UUID
    conn = connect()
    try:
        advocate_result = await advocate(conn, claim, UUID(debate_id))
        await skeptic(conn, debate_id, advocate_result)
        conclusion = await synthesizer(conn, debate_id, claim)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT agent, action, source_paper_id, detail "
                "FROM provenance WHERE debate_id = %s ORDER BY id",
                (debate_id,),
            )
            rows = cur.fetchall()
    finally:
        conn.close()

    transcript = [
        TranscriptEntry(
            agent=agent,
            action=action,
            detail=detail if detail is not None else {},
            source_paper_id=source_paper_id,
        )
        for agent, action, source_paper_id, detail in rows
    ]

    sources = [
        Source(paper_id=p["pmid"], title=p["title"], used_by=["advocate", "skeptic"])
        for p in advocate_result["papers"]
    ]

    return DebateResponse(
        debate_id=debate_id,
        claim=claim,
        conclusion=conclusion["conclusion"],
        verdict=conclusion["verdict"],
        confidence=conclusion["confidence"],
        confidence_rationale=conclusion["confidence_rationale"],
        driving_provenance_ids=conclusion["driving_provenance_ids"],
        transcript=transcript,
        sources=sources,
    )


async def background_debate(job_id: str, claim: str, multi_agent: bool = False) -> None:
    """Background task to run debate and store result."""
    cleanup_job_store()  # Periodic cleanup on each job
    debate_id = str(uuid4())
    job_store[job_id]["status"] = "running"
    job_store[job_id]["debate_id"] = debate_id
    job_store[job_id]["started_at"] = time.time()
    runtime_state.put_job(job_id, job_store[job_id])

    try:
        pipeline = run_debate_pipeline if multi_agent else run_synthesis_pipeline
        result = await pipeline(claim, debate_id)
        job_store[job_id]["status"] = "completed"
        job_store[job_id]["result"] = result.model_dump(mode="json")
        job_store[job_id]["completed_at"] = time.time()
        _remember(result, "multi_agent" if multi_agent else "single_call")
        # Multi-agent is the frozen evaluation subject and must stay uncached.
        if not multi_agent:
            _cache_put(get_claim_hash(claim), result)
    except Exception as e:
        job_store[job_id]["status"] = "failed"
        job_store[job_id]["error"] = str(e)
        job_store[job_id]["completed_at"] = time.time()
    finally:
        runtime_state.put_job(job_id, job_store[job_id])


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Configure structured logging
    log_level = os.environ.get("LOG_LEVEL", "INFO")
    json_logs = os.environ.get("JSON_LOGS", "false").lower() == "true"
    configure_logging(level=log_level, json_output=json_logs)
    runtime_state.ensure_schema()
    
    # Startup: ensure frontend build exists
    frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
    if os.path.exists(frontend_dist):
        app.mount("/", StaticFiles(directory=frontend_dist, html=True), name="frontend")
    yield
    # Shutdown cleanup
    job_store.clear()
    claim_cache.clear()


app = FastAPI(
    title="Aletheia",
    description="Multi-agent scientific reasoning system with full provenance traceability",
    version="0.1.0",
    lifespan=lifespan,
)

# Add request ID middleware
app.middleware("http")(request_id_middleware)

# CORS for frontend development - restrict in production
cors_origins = os.environ.get("CORS_ORIGINS", "http://localhost:3000,http://127.0.0.1:3000").split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AsyncDebateRequest(BaseModel):
    claim: str
    async_mode: bool = False
    multi_agent: bool = False  # False (default) = single_call; True = the eval harness's Advocate->Skeptic->Synthesizer pipeline


class JobStatusResponse(BaseModel):
    job_id: str
    status: str  # pending, running, completed, failed
    debate_id: str | None = None
    result: DebateResponse | None = None
    error: str | None = None
    created_at: float
    started_at: float | None = None
    completed_at: float | None = None
    cache_hit: bool = False


@app.post("/debate", response_model=DebateResponse)
async def debate_sync(request: DebateRequest) -> DebateResponse:
    """
    Synchronous debate endpoint. Runs single_call: real retrieval + one
    rubric-anchored Claude call (see app/agents/single_call.py's module
    docstring for why this is the default over the multi-agent pipeline).
    Uses caching for repeated claims.
    """
    claim = request.claim.strip()
    if not claim:
        raise HTTPException(status_code=400, detail="Claim cannot be empty")

    # Check cache
    claim_hash = get_claim_hash(claim)
    cached = _cache_get(claim_hash)
    if cached is not None:
        # Copy with a fresh debate_id for traceability. model_copy, not a
        # field-by-field reconstruction: the hand-copied version silently
        # dropped signal_breakdown when that field was added -- copying the
        # whole model means a future field can't be lost the same way.
        result = cached.model_copy(update={"debate_id": uuid4()})
        _remember(result, "single_call", from_cache=True)
        return result

    debate_id = str(uuid4())
    result = await run_synthesis_pipeline(claim, debate_id)
    _cache_put(claim_hash, result)
    _remember(result, "single_call")
    return result


@app.post("/debate/multi-agent", response_model=DebateResponse)
async def debate_multi_agent(request: DebateRequest) -> DebateResponse:
    """
    Runs the original Advocate -> Skeptic -> Synthesizer pipeline explicitly.
    Not the default (see POST /debate) -- kept reachable because it's the
    eval harness's (run_phase6.py) subject; the comparison against
    single_call only means something if this keeps running under the same
    conditions it was measured under. Expected latency: ~74 seconds.
    Not cached, unlike /debate, so eval runs always get a fresh pass.
    """
    claim = request.claim.strip()
    if not claim:
        raise HTTPException(status_code=400, detail="Claim cannot be empty")

    debate_id = str(uuid4())
    result = await run_debate_pipeline(claim, debate_id)
    _remember(result, "multi_agent")
    return result


@app.post("/debate/async", response_model=JobStatusResponse)
async def debate_async(request: AsyncDebateRequest, background_tasks: BackgroundTasks) -> JobStatusResponse:
    """
    Asynchronous debate endpoint. Submits job to background queue and returns job ID.
    Poll /debate/jobs/{job_id} for status. Better for production use.
    """
    claim = request.claim.strip()
    if not claim:
        raise HTTPException(status_code=400, detail="Claim cannot be empty")

    # Check cache first
    claim_hash = get_claim_hash(claim)
    cached = _cache_get(claim_hash)
    if cached is not None:
        new_debate_id = uuid4()
        result = cached.model_copy(update={"debate_id": new_debate_id})
        _remember(result, "single_call", from_cache=True)
        return JobStatusResponse(
            job_id=str(uuid4()),
            status="completed",
            debate_id=str(new_debate_id),
            result=result,
            error=None,
            created_at=time.time(),
            started_at=time.time(),
            completed_at=time.time(),
            cache_hit=True,
        )

    job_id = str(uuid4())
    job_store[job_id] = {
        "status": "pending",
        "claim": claim,
        "multi_agent": request.multi_agent,
        "created_at": time.time(),
    }
    runtime_state.put_job(job_id, job_store[job_id])

    background_tasks.add_task(background_debate, job_id, claim, request.multi_agent)

    return JobStatusResponse(
        job_id=job_id,
        status="pending",
        debate_id=None,
        result=None,
        error=None,
        created_at=job_store[job_id]["created_at"],
    )


@app.get("/debate/jobs/{job_id}", response_model=JobStatusResponse)
async def get_job_status(job_id: str) -> JobStatusResponse:
    """Poll for async debate job status."""
    job = runtime_state.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job not found")
    return JobStatusResponse(
        job_id=job_id,
        status=job["status"],
        debate_id=job.get("debate_id"),
        result=DebateResponse(**job["result"]) if job.get("result") else None,
        error=job.get("error"),
        created_at=job["created_at"],
        started_at=job.get("started_at"),
        completed_at=job.get("completed_at"),
    )


@app.get("/debate/jobs")
async def list_jobs(limit: int = 50, offset: int = 0) -> dict:
    """List recent debate jobs."""
    total, jobs = runtime_state.list_jobs(min(max(limit, 1), 100), max(offset, 0))
    return {"total": total, "jobs": jobs}


@app.delete("/debate/jobs/{job_id}")
async def delete_job(job_id: str) -> dict:
    """Delete a job from the store."""
    if not runtime_state.delete_job(job_id):
        raise HTTPException(status_code=404, detail="Job not found")
    return {"deleted": job_id}


@app.get("/memory/research")
async def list_research_memory(limit: int = Query(20, ge=1, le=100)) -> dict:
    """Return compact metadata for recent analyses, newest first."""
    memories = runtime_state.list_memories(limit)
    return {"items": memories, "total": len(memories)}


@app.get("/memory/research/{debate_id}", response_model=DebateResponse)
async def get_research_memory(debate_id: str) -> DebateResponse:
    """Reopen the exact response saved for a prior analysis."""
    payload = runtime_state.get_memory(debate_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="Research memory not found")
    return DebateResponse(**payload)


@app.delete("/memory/research/{debate_id}")
async def delete_research_memory(debate_id: str) -> dict:
    if not runtime_state.delete_memory(debate_id):
        raise HTTPException(status_code=404, detail="Research memory not found")
    return {"deleted": debate_id}


@app.post("/cache/clear")
async def clear_cache() -> dict:
    """Clear the claim response cache."""
    count = len(claim_cache) + runtime_state.clear_responses()
    claim_cache.clear()
    # Note: embedding_cache is now in embeddings module
    return {"cleared_entries": count}


@app.post("/cache/embeddings/clear")
async def clear_embedding_cache_endpoint() -> dict:
    """Clear the embedding cache."""
    count = clear_embedding_cache()
    return {"cleared_entries": count}


@app.get("/cache/stats")
async def cache_stats() -> dict:
    """Get cache statistics."""
    emb_stats = get_embedding_cache_stats()
    return {
        "claim_cache_size": len(claim_cache),
        "claim_cache": claim_cache.stats(),
        "persistent_cache": runtime_state.persistence_available,
        "embedding_cache_size": emb_stats["size"],
        "job_store_size": len(job_store),
        "job_store": job_store.stats(),
    }


@app.get("/health")
async def health_check() -> dict:
    """Health check endpoint."""
    emb_stats = get_embedding_cache_stats()
    return {
        "status": "healthy",
        "service": "aletheia",
        "version": "0.1.0",
        "cache_stats": {
            "claims": len(claim_cache),
            "embeddings": emb_stats["size"],
            "jobs": len(job_store),
        },
        "infrastructure": {
            "api": "operational",
            "persistence": "postgres" if runtime_state.persistence_available else "memory-fallback",
            "cache": "l1-ttl + postgres-l2",
            "queue": "background-worker + durable-ledger",
            "llm": get_runtime_config(),
        },
    }


# Include batch router
from app.batch import router as batch_router
app.include_router(batch_router)

# Serve frontend in production
frontend_dist = os.path.join(os.path.dirname(__file__), "..", "..", "frontend", "dist")
if os.path.exists(frontend_dist):
    app.mount("/static", StaticFiles(directory=frontend_dist), name="static")

    @app.get("/{full_path:path}")
    async def serve_frontend(full_path: str):
        """Serve React frontend for all non-API routes."""
        if full_path.startswith("api/") or full_path.startswith("debate") or full_path.startswith("health") or full_path.startswith("cache"):
            raise HTTPException(status_code=404, detail="Not found")
        index_path = os.path.join(frontend_dist, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        raise HTTPException(status_code=404, detail="Frontend not built")
