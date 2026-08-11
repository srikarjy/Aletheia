"""Default reasoning path, resolving the conflict between README.md's
Advocate->Skeptic->Synthesizer debate description and this project's own
Phase 6 eval finding: run_phase6.py's real harness run (n=10, real Claude
calls, real PubMed retrieval) found debate did NOT measurably beat a single
well-prompted call -- see README.md's Results & Limitations. Continuing to
default to three sequential LLM calls with no measured benefit over one
isn't defensible on cost or latency grounds, so this is the default now.

This is not "debate was wrong, delete it" -- the debate pipeline
(app/agents/advocate.py, skeptic.py, synthesizer.py) stays as-is, reachable
via POST /debate/multi-agent, because it's still the eval harness's subject
and the comparison only means something if both sides keep running under
the same conditions they were measured under.

What single_call keeps from the debate pipeline, deliberately, because
these are the parts that were actually earning their keep, not the
three-agent structure itself:
  - real grounded retrieval (search_pubmed) with a provenance "retrieve"
    row per paper, same as advocate.py
  - rubric-anchored confidence (rubric v1, verbatim from
    SYNTHESIZER_PROMPT_TEMPLATE) instead of an unstructured confidence
  - code-enforced citation integrity: cited_pmids must be real PMIDs from
    this call's retrieval, or the call is rejected and retried once with a
    correction, exactly as synthesizer.py enforces driving_provenance_ids
  - the response is reconstructed from the provenance rows this function
    writes, so the transcript the caller sees is the audit trail, not a
    parallel summary that could drift from it -- same invariant main.py's
    module docstring states for the debate pipeline
"""

import json
from uuid import UUID

import psycopg

from app.embeddings import embed
from app.llm import call_tool, _client as llm_client
from app.mcp_client import search_pubmed
from app.prompts import prompt_hash

MODEL = "claude-sonnet-4-5"
AGENT_ID = "aletheia:single_call"

# Rubric v1, unchanged from SYNTHESIZER_PROMPT_TEMPLATE (see prompts.py's
# comment on why it's frozen) -- reproduced here rather than imported+sliced
# because the debate version's Step 1 is written in terms of "the skeptic's
# challenges," which doesn't exist in a single pass. The anchors (A-D) and
# what each means are otherwise identical, so scores from either path stay
# comparable, which is the property the eval harness depends on.
SINGLE_CALL_PROMPT_TEMPLATE = """You are evaluating a scientific claim against retrieved evidence. Build the case for the claim, actively look for evidence that conflicts with it or with other retrieved papers, then resolve to a conclusion and confidence following the rubric below exactly.

Claim: {claim}

Retrieved evidence:
{evidence_block}

CONFIDENCE RUBRIC v1

"confidence" means: the degree to which the claim is supported by the evidence above, after actively checking for conflicting or contradicting evidence among the retrieved papers. It is NOT a probability that the claim is true in the world.

Step 1 — contradiction screen. Check whether any retrieved paper conflicts with another, or conflicts with the claim itself, or is too weak a study type / too small a sample to support what's being claimed. Only count a weakness if it's actually present in the cited text, not a hypothetical concern.

Step 2 — place the claim against the anchors, using only real weaknesses found in Step 1:

  A. A real weakness directly undermines the central evidence for the claim (e.g. the key citation does not say what it's being used to support) → confidence <= 0.3
  B. Retrieved papers genuinely conflict on the central claim and neither side is invalidated → confidence 0.4-0.6, verdict "unresolved" — state explicitly that the conflict could not be resolved.
  C. Real weaknesses exist but touch only peripheral points; the central citations hold → confidence 0.5-0.7
  D. No real substantive weaknesses and the central citations hold up → confidence >= 0.8

Anchors are cases, not a partition: where bands overlap (0.5-0.6), the verdict distinguishes them. Values in the gaps (0.3-0.4, 0.7-0.8) are allowed only by naming the nearest anchor and justifying the offset in confidence_rationale.

If the evidence doesn't actually support the claim, or is too thin to judge, say so honestly in conclusion rather than overstating it.

confidence_rationale must name the anchor letter applied. cited_pmids must list only PMIDs that appear in the evidence above.

Submit your resolution using the resolve_claim tool."""

RESOLVE_CLAIM_TOOL = {
    "name": "resolve_claim",
    "description": "Submit the resolved conclusion + rubric-anchored confidence for the claim.",
    "input_schema": {
        "type": "object",
        "properties": {
            "conclusion": {
                "type": "string",
                "description": "The structured conclusion resolving (or explicitly failing to resolve) the claim.",
            },
            "verdict": {
                "type": "string",
                "enum": ["supported", "unresolved", "refuted"],
                "description": "supported = evidence backs the claim; unresolved = genuine conflict per anchor B; refuted = a real weakness undermines the central evidence.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in [0,1] placed against rubric v1's anchors A-D.",
            },
            "confidence_rationale": {
                "type": "string",
                "description": "Must name the anchor letter applied.",
            },
            "cited_pmids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "PMIDs from the retrieved evidence that drove the conclusion and confidence.",
            },
        },
        "required": [
            "conclusion",
            "verdict",
            "confidence",
            "confidence_rationale",
            "cited_pmids",
        ],
    },
}


def _format_evidence(papers: list[dict]) -> str:
    return "\n\n".join(f"PMID {p['pmid']}: {p['title']}\n{p['abstract']}" for p in papers)


async def single_call(conn: psycopg.Connection, claim: str, debate_id: UUID) -> dict:
    """Retrieve evidence, then resolve the claim in one Claude call. Returns
    a dict shaped like synthesizer()'s + advocate()'s combined output plus
    "papers", so main.py can build a DebateResponse the same way it does
    for the multi-agent pipeline."""
    result = await search_pubmed(claim, agent_id=AGENT_ID)
    papers = result["papers"]

    pmid_to_provenance_id: dict[str, int] = {}
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
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (
                    str(debate_id),
                    claim,
                    "single_call",
                    "retrieve",
                    paper["pmid"],
                    paper["retrieval_id"],
                    json.dumps({"title": paper["title"]}),
                ),
            )
            pmid_to_provenance_id[paper["pmid"]] = cur.fetchone()[0]
    conn.commit()

    evidence_block = _format_evidence(papers)
    prompt = SINGLE_CALL_PROMPT_TEMPLATE.format(claim=claim, evidence_block=evidence_block)
    valid_pmids = set(pmid_to_provenance_id)

    resolution = call_tool(
        llm_client,
        MODEL,
        tool_name="resolve_claim",
        tool_schema=RESOLVE_CLAIM_TOOL["input_schema"],
        prompt=prompt,
    )
    bad = [p for p in resolution["cited_pmids"] if p not in valid_pmids]
    if bad:
        # Same citation-integrity enforcement as synthesizer.py: one
        # corrective retry, then fail loudly rather than persist an
        # unauditable "conclude" row.
        correction = (
            f"\n\nCORRECTION: cited_pmids {bad} are not PMIDs from the retrieved evidence "
            f"above. Valid PMIDs are {sorted(valid_pmids)}. Resubmit citing only those."
        )
        resolution = call_tool(
            llm_client,
            MODEL,
            tool_name="resolve_claim",
            tool_schema=RESOLVE_CLAIM_TOOL["input_schema"],
            prompt=prompt + correction,
        )
        bad = [p for p in resolution["cited_pmids"] if p not in valid_pmids]
        if bad:
            raise RuntimeError(
                f"single_call cited PMIDs {bad} not present in this call's retrieval "
                f"for debate {debate_id} after a corrective retry — refusing to persist "
                f"an unauditable confidence."
            )

    driving_provenance_ids = [pmid_to_provenance_id[p] for p in resolution["cited_pmids"]]

    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO provenance "
            "(debate_id, claim, agent, action, source_paper_id, detail, prompt_version) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (
                str(debate_id),
                claim,
                "single_call",
                "conclude",
                None,
                json.dumps(resolution),
                prompt_hash(SINGLE_CALL_PROMPT_TEMPLATE),
            ),
        )
    conn.commit()

    return {
        "conclusion": resolution["conclusion"],
        "verdict": resolution["verdict"],
        "confidence": resolution["confidence"],
        "confidence_rationale": resolution["confidence_rationale"],
        "driving_provenance_ids": driving_provenance_ids,
        "papers": papers,
    }
