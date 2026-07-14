"""Phase 2: the advocate agent — cognitive operations #1 (retrieval) + #2 (evidence
appraisal), per README. Writes a provenance row for every action, not just the final
output (BLUEPRINT.md Phase 2 exit criteria): one "retrieve" row per paper (each with
a real source_paper_id + retrieval_id), then one "appraise" row for the case itself.

The "appraise" row has source_paper_id=NULL by design, not by omission: it isn't
about one paper, it's a synthesis across however many papers got cited. The papers it
draws on are recorded twice — individually in the "retrieve" rows' source_paper_id
(so each is still linked to a real source), and together in this row's `detail.cited_pmids`
(so the synthesis itself is reconstructable). A single source_paper_id column can't
represent "these N papers," so this is the honest way to represent it, not a shortcut.
"""

import json
import os
from uuid import UUID

import psycopg
from anthropic import Anthropic

from app.embeddings import embed
from app.llm import call_tool
from app.mcp_client import search_pubmed
from app.prompts import ADVOCATE_PROMPT_TEMPLATE, prompt_hash

ADVOCATE_AGENT_ID = "aletheia:advocate"
MODEL = "claude-sonnet-4-5"

BUILD_CASE_TOOL = {
    "name": "build_case",
    "description": "Submit the evidence-based case for the claim.",
    "input_schema": {
        "type": "object",
        "properties": {
            "case_summary": {
                "type": "string",
                "description": "The evidence-based argument for the claim, in prose.",
            },
            "cited_pmids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "PMIDs from the retrieved evidence actually used in the case.",
            },
        },
        "required": ["case_summary", "cited_pmids"],
    },
}

_client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])


async def advocate(conn: psycopg.Connection, claim: str, debate_id: UUID) -> dict:
    result = await search_pubmed(claim, agent_id=ADVOCATE_AGENT_ID)
    papers = result["papers"]

    with conn.cursor() as cur:
        for paper in papers:
            vector = embed(paper["abstract"])
            cur.execute(
                "INSERT INTO embeddings (paper_id, embedding, metadata, content) "
                "VALUES (%s, %s, %s, %s)",
                (
                    paper["pmid"],
                    vector,
                    json.dumps({"title": paper["title"]}),
                    paper["abstract"],
                ),
            )
            cur.execute(
                "INSERT INTO provenance "
                "(debate_id, claim, agent, action, source_paper_id, retrieval_id, detail) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    str(debate_id),
                    claim,
                    "advocate",
                    "retrieve",
                    paper["pmid"],
                    paper["retrieval_id"],
                    json.dumps({"title": paper["title"]}),
                ),
            )
    conn.commit()

    evidence_block = "\n\n".join(
        f"PMID {p['pmid']}: {p['title']}\n{p['abstract']}" for p in papers
    )
    prompt = ADVOCATE_PROMPT_TEMPLATE.format(claim=claim, evidence_block=evidence_block)

    case = call_tool(_client, MODEL, 2048, BUILD_CASE_TOOL, prompt)

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO provenance "
            "(debate_id, claim, agent, action, source_paper_id, retrieval_id, detail, prompt_version) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                str(debate_id),
                claim,
                "advocate",
                "appraise",
                None,
                None,
                json.dumps(case),
                prompt_hash(ADVOCATE_PROMPT_TEMPLATE),
            ),
        )
    conn.commit()

    return {"claim": claim, "papers": papers, "case": case}
