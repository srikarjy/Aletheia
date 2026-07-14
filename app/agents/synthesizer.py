"""Phase 4: the synthesizer agent. Reads the full debate transcript (the provenance
rows the advocate and skeptic already wrote for this debate_id) and resolves it into a
structured conclusion + a confidence number produced by rubric v1 (Q4a, QUESTIONS.md#q4).
Does NOT retrieve new evidence — it reasons only over the transcript (BLUEPRINT.md Phase 4).

Two things make the confidence "a rule, not vibes":
  1. The rubric is embedded verbatim in SYNTHESIZER_PROMPT_TEMPLATE, so the band the
     model picks is checkable against a written standard and versioned by Q7's hash.
  2. driving_provenance_ids is CODE-enforced, not honor-system: every id the model cites
     must be a real provenance row in THIS debate, or the call is rejected and retried
     once with a correction. A hallucinated or cross-debate id never reaches the "conclude"
     row — that's the difference between auditable and merely decorated.
"""

import json
import os
from uuid import UUID

import psycopg
from anthropic import Anthropic

from app.llm import call_tool
from app.prompts import SYNTHESIZER_PROMPT_TEMPLATE, prompt_hash

MODEL = "claude-sonnet-4-5"

SYNTHESIZE_TOOL = {
    "name": "synthesize",
    "description": "Submit the resolved conclusion + rubric-anchored confidence for the debate.",
    "input_schema": {
        "type": "object",
        "properties": {
            "conclusion": {
                "type": "string",
                "description": "The structured conclusion resolving (or explicitly failing to resolve) the debate.",
            },
            "verdict": {
                "type": "string",
                "enum": ["supported", "unresolved", "refuted"],
                "description": "supported = evidence backs the claim; unresolved = genuine conflict per anchor B; refuted = a valid challenge undermines the central evidence.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in [0,1] placed against rubric v1's anchors A-D.",
            },
            "confidence_rationale": {
                "type": "string",
                "description": "Must name the anchor letter applied and the transcript rows that drove the placement.",
            },
            "driving_provenance_ids": {
                "type": "array",
                "items": {"type": "integer"},
                "description": "Provenance row ids (from the bracketed transcript) that drove the confidence number.",
            },
        },
        "required": [
            "conclusion",
            "verdict",
            "confidence",
            "confidence_rationale",
            "driving_provenance_ids",
        ],
    },
}

_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


def _load_transcript(conn: psycopg.Connection, debate_id: UUID) -> list[dict]:
    """The transcript IS the provenance rows for this debate, in order. Each row's id
    is what the synthesizer must cite in driving_provenance_ids."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, agent, action, source_paper_id, detail "
            "FROM provenance WHERE debate_id = %s ORDER BY id",
            (str(debate_id),),
        )
        rows = cur.fetchall()
    return [
        {"id": r[0], "agent": r[1], "action": r[2], "source_paper_id": r[3], "detail": r[4]}
        for r in rows
    ]


def _format_transcript(rows: list[dict]) -> str:
    lines = []
    for r in rows:
        detail = json.dumps(r["detail"]) if r["detail"] is not None else "{}"
        src = f" source_paper_id={r['source_paper_id']}" if r["source_paper_id"] else ""
        lines.append(f"[{r['id']}] agent={r['agent']} action={r['action']}{src}\n    {detail}")
    return "\n\n".join(lines)


async def synthesizer(conn: psycopg.Connection, debate_id: UUID, claim: str) -> dict:
    rows = _load_transcript(conn, debate_id)
    valid_ids = {r["id"] for r in rows}
    transcript_block = _format_transcript(rows)
    prompt = SYNTHESIZER_PROMPT_TEMPLATE.format(claim=claim, transcript_block=transcript_block)

    result = call_tool(_client, MODEL, 2048, SYNTHESIZE_TOOL, prompt)
    bad = [i for i in result["driving_provenance_ids"] if i not in valid_ids]
    if bad:
        # Enforce citation integrity: one corrective retry naming the offending ids, then
        # fail loudly rather than persist a "conclude" row that cites rows not in this debate.
        correction = (
            f"\n\nCORRECTION: driving_provenance_ids {bad} are not rows in this debate's "
            f"transcript. Valid ids are {sorted(valid_ids)}. Resubmit citing only those."
        )
        result = call_tool(_client, MODEL, 2048, SYNTHESIZE_TOOL, prompt + correction)
        bad = [i for i in result["driving_provenance_ids"] if i not in valid_ids]
        if bad:
            raise RuntimeError(
                f"Synthesizer cited provenance ids {bad} not present in debate {debate_id} "
                f"after a corrective retry — refusing to persist an unauditable confidence."
            )

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO provenance "
            "(debate_id, claim, agent, action, source_paper_id, detail, prompt_version) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                str(debate_id),
                claim,
                "synthesizer",
                "conclude",
                None,
                json.dumps(result),
                prompt_hash(SYNTHESIZER_PROMPT_TEMPLATE),
            ),
        )
    conn.commit()

    return result
