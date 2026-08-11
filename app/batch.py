"""Batch processing endpoints for evaluation and scaling."""

from fastapi import APIRouter, HTTPException, BackgroundTasks
from pydantic import BaseModel
from typing import Optional
import asyncio
import time

from app.claims import get_all_claims, EvalClaim
from app.main import run_debate_pipeline, run_synthesis_pipeline, background_debate, job_store

router = APIRouter(prefix="/batch", tags=["batch"])


class BatchRequest(BaseModel):
    claims: list[str]
    async_mode: bool = True


class BatchJobResponse(BaseModel):
    batch_id: str
    status: str
    total_claims: int
    completed: int
    failed: int
    results: list[dict] = []


batch_jobs: dict[str, dict] = {}


@router.post("/debate", response_model=BatchJobResponse)
async def batch_debate(request: BatchRequest, background_tasks: BackgroundTasks) -> BatchJobResponse:
    """Submit multiple claims for batch debate processing."""
    if not request.claims:
        raise HTTPException(status_code=400, detail="No claims provided")
    if len(request.claims) > 50:
        raise HTTPException(status_code=400, detail="Maximum 50 claims per batch")

    batch_id = f"batch_{int(time.time() * 1000)}"
    batch_jobs[batch_id] = {
        "status": "pending",
        "claims": request.claims,
        "total": len(request.claims),
        "completed": 0,
        "failed": 0,
        "results": [],
        "created_at": time.time(),
    }

    if request.async_mode:
        background_tasks.add_task(process_batch, batch_id)
    else:
        # Run synchronously (for small batches)
        await process_batch(batch_id)

    return BatchJobResponse(
        batch_id=batch_id,
        status=batch_jobs[batch_id]["status"],
        total_claims=batch_jobs[batch_id]["total"],
        completed=batch_jobs[batch_id]["completed"],
        failed=batch_jobs[batch_id]["failed"],
        results=batch_jobs[batch_id]["results"],
    )


async def process_batch(batch_id: str, multi_agent: bool = False) -> None:
    """Process a batch of claims sequentially. multi_agent=True runs the
    eval harness's Advocate->Skeptic->Synthesizer pipeline (used by
    /eval/run, which is specifically evaluating it); everything else
    defaults to single_call, same as POST /debate."""
    job = batch_jobs[batch_id]
    job["status"] = "running"
    job["started_at"] = time.time()
    pipeline = run_debate_pipeline if multi_agent else run_synthesis_pipeline

    for i, claim in enumerate(job["claims"]):
        debate_id = f"{batch_id}_{i}"
        try:
            result = await pipeline(claim, debate_id)
            job["results"].append({
                "index": i,
                "claim": claim,
                "status": "completed",
                "result": result.model_dump(),
            })
            job["completed"] += 1
        except Exception as e:
            job["results"].append({
                "index": i,
                "claim": claim,
                "status": "failed",
                "error": str(e),
            })
            job["failed"] += 1

    job["status"] = "completed"
    job["completed_at"] = time.time()


@router.get("/debate/{batch_id}", response_model=BatchJobResponse)
async def get_batch_status(batch_id: str) -> BatchJobResponse:
    """Get batch processing status."""
    if batch_id not in batch_jobs:
        raise HTTPException(status_code=404, detail="Batch not found")

    job = batch_jobs[batch_id]
    return BatchJobResponse(
        batch_id=batch_id,
        status=job["status"],
        total_claims=job["total"],
        completed=job["completed"],
        failed=job["failed"],
        results=job["results"],
    )


@router.post("/eval/run")
async def run_full_eval(background_tasks: BackgroundTasks) -> dict:
    """Run the full 5-claim evaluation set (Phase 5)."""
    claims = get_all_claims()
    claim_strings = [c.claim for c in claims]
    
    batch_id = f"eval_{int(time.time() * 1000)}"
    batch_jobs[batch_id] = {
        "status": "pending",
        "claims": claim_strings,
        "claim_metadata": [{"id": c.id, "category": c.category, "expected": c.expected_verdict} for c in claims],
        "total": len(claims),
        "completed": 0,
        "failed": 0,
        "results": [],
        "created_at": time.time(),
        "is_eval": True,
    }
    
    background_tasks.add_task(process_batch, batch_id, True)  # multi_agent=True: this endpoint evaluates the debate pipeline specifically

    return {
        "batch_id": batch_id,
        "message": "Evaluation started. Poll /batch/debate/{batch_id} for status.",
        "claims": len(claims),
    }


@router.get("/eval/claims")
async def list_eval_claims() -> dict:
    """List the 5 curated evaluation claims with metadata."""
    claims = get_all_claims()
    return {
        "claims": [
            {
                "id": c.id,
                "claim": c.claim,
                "category": c.category,
                "rationale": c.rationale,
                "expected_verdict": c.expected_verdict,
                "known_facts": c.known_facts,
            }
            for c in claims
        ]
    }