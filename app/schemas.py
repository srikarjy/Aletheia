"""Pydantic models for the POST /debate contract defined in DESIGN.md.

Phase 4 wires the real advocate -> skeptic -> synthesizer pipeline behind this
contract. The confidence fields carry rubric v1's output (Q4a, QUESTIONS.md#q4):
`confidence` is placed against written anchors, `confidence_rationale` names the
anchor, and `driving_provenance_ids` are the code-validated rows behind the number
so "why 0.4 and not 0.7" is a row you can point at, not buried in the model's head.
"""

from uuid import UUID

from pydantic import BaseModel, Field


class DebateRequest(BaseModel):
    claim: str = Field(..., min_length=1)


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
    verdict: str
    confidence: float
    confidence_rationale: str
    driving_provenance_ids: list[int]
    transcript: list[TranscriptEntry]
    sources: list[Source]
