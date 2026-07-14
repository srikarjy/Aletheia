"""Phase 3: the skeptic agent. Reads the advocate's case + the same evidence the
advocate already retrieved (no new retrieval — see BLUEPRINT.md Phase 3: minimal
version, re-retrieval deferred until a real case demonstrates existing evidence is
insufficient to mount a real challenge).

Provenance mirrors the advocate's per-item + summary pattern: one "critique" row per
concrete challenge (source_paper_id set when the challenge targets one paper), then
one "assess" row for the overall verdict + uncertainty notes.
"""

import json
import os
from uuid import UUID

import psycopg
from anthropic import Anthropic

from app.llm import call_tool
from app.prompts import SKEPTIC_PROMPT_TEMPLATE, prompt_hash

MODEL = "claude-sonnet-4-5"

RAISE_CHALLENGES_TOOL = {
    "name": "raise_challenges",
    "description": "Submit the skeptic's critique of the advocate's case.",
    "input_schema": {
        "type": "object",
        "properties": {
            "challenges": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "target_pmid": {
                            "type": "string",
                            "description": "The cited paper this challenge targets, if specific to one. Omit if the challenge is cross-cutting.",
                        },
                        "issue": {
                            "type": "string",
                            "description": "The concrete, evidence-based objection.",
                        },
                    },
                    "required": ["issue"],
                },
                "description": "Concrete challenges against the case. Empty array is valid if the case genuinely holds up.",
            },
            "uncertainty_notes": {
                "type": "string",
                "description": "What remains genuinely unknown or unaddressed by the cited evidence.",
            },
            "overall_assessment": {
                "type": "string",
                "description": "Honest verdict on how well the evidence actually supports the claim.",
            },
        },
        "required": ["challenges", "uncertainty_notes", "overall_assessment"],
    },
}

_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


async def skeptic(conn: psycopg.Connection, debate_id: UUID, advocate_result: dict) -> dict:
    claim = advocate_result["claim"]
    case = advocate_result["case"]
    papers = advocate_result["papers"]

    evidence_block = "\n\n".join(
        f"PMID {p['pmid']}: {p['title']}\n{p['abstract']}" for p in papers
    )
    prompt = SKEPTIC_PROMPT_TEMPLATE.format(
        claim=claim, case_summary=case["case_summary"], evidence_block=evidence_block
    )

    critique = call_tool(_client, MODEL, 2048, RAISE_CHALLENGES_TOOL, prompt)
    version = prompt_hash(SKEPTIC_PROMPT_TEMPLATE)

    with conn.cursor() as cur:
        for challenge in critique["challenges"]:
            cur.execute(
                "INSERT INTO provenance "
                "(debate_id, claim, agent, action, source_paper_id, detail, prompt_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    str(debate_id),
                    claim,
                    "skeptic",
                    "critique",
                    challenge.get("target_pmid"),
                    json.dumps({"issue": challenge["issue"]}),
                    version,
                ),
            )
        cur.execute(
            "INSERT INTO provenance "
            "(debate_id, claim, agent, action, source_paper_id, detail, prompt_version) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                str(debate_id),
                claim,
                "skeptic",
                "assess",
                None,
                json.dumps(
                    {
                        "uncertainty_notes": critique["uncertainty_notes"],
                        "overall_assessment": critique["overall_assessment"],
                    }
                ),
                version,
            ),
        )
    conn.commit()

    return critique
