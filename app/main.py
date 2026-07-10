"""Phase 0 skeleton: proves the API contract round-trips before any agent,
retrieval, or DB logic exists. See BLUEPRINT.md Phase 0 exit criteria.
"""

from uuid import uuid4

from fastapi import FastAPI

from app.schemas import DebateRequest, DebateResponse, Source, TranscriptEntry

app = FastAPI(title="Aletheia")


@app.post("/debate", response_model=DebateResponse)
def debate(request: DebateRequest) -> DebateResponse:
    return DebateResponse(
        debate_id=uuid4(),
        claim=request.claim,
        conclusion="FIXTURE: no agent loop exists yet (Phase 0).",
        confidence=0.0,
        transcript=[
            TranscriptEntry(
                agent="advocate",
                action="retrieve",
                detail={"note": "fixture data, Phase 1 will call Biolab MCP"},
                source_paper_id="PMID_FIXTURE",
            ),
        ],
        sources=[
            Source(paper_id="PMID_FIXTURE", title="Fixture source", used_by=["advocate"]),
        ],
    )
