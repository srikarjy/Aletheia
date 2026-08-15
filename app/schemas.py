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
    # Retraction screen results (PubMed record markers, checked at retrieval
    # time). False + no notice can also mean the status was unknown (screen
    # degraded, or a non-PubMed source) -- retracted=True is always real.
    retracted: bool = False
    concern: bool = False
    retraction_notice: str | None = None


class SignalBreakdown(BaseModel):
    """Per-evidence-type support scores from single_call, each scored only
    from evidence types actually present in that call's retrieval (0.0 for an
    absent type). Additive to the rubric-v1 scalar `confidence`, which is
    unchanged — this exists so a frontend can render four honest bars instead
    of faking four from one number. None on the multi-agent path, whose
    synthesizer predates (and, as the frozen eval subject, doesn't adopt)
    this field."""

    literature: float = Field(..., ge=0, le=1)
    protein_evidence: float = Field(..., ge=0, le=1)
    clinical_evidence: float = Field(..., ge=0, le=1)
    llm_rating: float = Field(..., ge=0, le=1)


class DebateResponse(BaseModel):
    debate_id: UUID
    claim: str
    conclusion: str
    verdict: str
    confidence: float
    confidence_rationale: str
    signal_breakdown: SignalBreakdown | None = None
    driving_provenance_ids: list[int]
    transcript: list[TranscriptEntry]
    sources: list[Source]
