"""Pydantic models for the POST /debate contract defined in DESIGN.md.

Phase 0 only: no agent logic exists yet, so these models exist purely to
pin down the response shape before any implementation is built against it.
"""

from uuid import UUID

from pydantic import BaseModel


class DebateRequest(BaseModel):
    claim: str


class TranscriptEntry(BaseModel):
    agent: str
    action: str
    detail: dict
    source_paper_id: str | None = None


class Source(BaseModel):
    paper_id: str
    title: str
    used_by: list[str]


class DebateResponse(BaseModel):
    debate_id: UUID
    claim: str
    conclusion: str
    confidence: float
    transcript: list[TranscriptEntry]
    sources: list[Source]
