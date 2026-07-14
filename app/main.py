"""Phase 4: POST /debate runs the real advocate -> skeptic -> synthesizer pipeline
end to end (BLUEPRINT.md Phase 4 exit criteria), no fixtures. Q5 decided this is a
fixed single pass each, in order. Q8 (sync vs async) stays synchronous until a real
latency number says otherwise — this endpoint is where that number gets measured.

The response is reconstructed from the provenance rows the three agents wrote, so the
transcript the caller sees is literally the audit trail, not a parallel summary that
could drift from it.
"""

from uuid import uuid4

from fastapi import FastAPI

from app.agents.advocate import advocate
from app.agents.skeptic import skeptic
from app.agents.synthesizer import synthesizer
from app.db import connect
from app.schemas import DebateRequest, DebateResponse, Source, TranscriptEntry

app = FastAPI(title="Aletheia")


@app.post("/debate", response_model=DebateResponse)
async def debate(request: DebateRequest) -> DebateResponse:
    debate_id = uuid4()
    conn = connect()
    try:
        advocate_result = await advocate(conn, request.claim, debate_id)
        await skeptic(conn, debate_id, advocate_result)
        conclusion = await synthesizer(conn, debate_id, request.claim)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT agent, action, source_paper_id, detail "
                "FROM provenance WHERE debate_id = %s ORDER BY id",
                (str(debate_id),),
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

    # Sources are the papers the advocate retrieved; both agents reason over the same
    # evidence block, so both are honest members of used_by.
    sources = [
        Source(paper_id=p["pmid"], title=p["title"], used_by=["advocate", "skeptic"])
        for p in advocate_result["papers"]
    ]

    return DebateResponse(
        debate_id=debate_id,
        claim=request.claim,
        conclusion=conclusion["conclusion"],
        verdict=conclusion["verdict"],
        confidence=conclusion["confidence"],
        confidence_rationale=conclusion["confidence_rationale"],
        driving_provenance_ids=conclusion["driving_provenance_ids"],
        transcript=transcript,
        sources=sources,
    )
