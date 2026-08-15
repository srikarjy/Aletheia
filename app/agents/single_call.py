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
from app.prompts import CONFIDENCE_RUBRIC_V1, prompt_hash

MODEL = "claude-sonnet-4-5"
AGENT_ID = "aletheia:single_call"

# Rubric v1, imported verbatim from app.prompts.CONFIDENCE_RUBRIC_V1 (see that
# module's comment on why it's frozen) rather than hand-copied here, so an edit
# to the rubric applies to both reasoning paths by construction instead of
# risking silent drift between two copies. Only the Step 1 framing differs --
# this path has no skeptic, so it's phrased as a self-directed contradiction
# screen -- the anchors (A-D) are identical, which is the property the eval
# harness's comparison depends on.
SINGLE_CALL_PROMPT_TEMPLATE = """You are evaluating a scientific claim against retrieved evidence. Build the case for the claim, actively look for evidence that conflicts with it or with other retrieved papers, then resolve to a conclusion and confidence following the rubric below exactly.

Claim: {claim}

Retrieved evidence:
{evidence_block}

""" + CONFIDENCE_RUBRIC_V1.format(
    validity_screen_step="Step 1 — contradiction screen. Check whether any retrieved paper conflicts with another, or conflicts with the claim itself, or is too weak a study type / too small a sample to support what's being claimed. Only count a weakness if it's actually present in the cited text, not a hypothetical concern."
) + """

If the evidence doesn't actually support the claim, or is too thin to judge, say so honestly in conclusion rather than overstating it.

confidence_rationale must name the anchor letter applied. cited_pmids must list only PMIDs that appear in the evidence above.

signal_breakdown scores how strongly each evidence TYPE present in the retrieval above supports the claim, each in [0,1]. Score only from what the retrieved abstracts actually report — never from background knowledge:
- literature: breadth and consistency of independent published support across the retrieved papers.
- protein_evidence: structural, mutagenesis, binding, or other biophysical data reported in the retrieved abstracts. 0.0 if none of the abstracts report any.
- clinical_evidence: patient outcomes, trial data, or real-world evidence reported in the retrieved abstracts. 0.0 if none report any.
- llm_rating: your own self-assessment of this resolution. This is weighted at most 15% downstream, so score it honestly rather than defensively.
A 0.0 for an absent evidence type is the correct answer, not a failure.

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
            "signal_breakdown": {
                "type": "object",
                "description": "Per-evidence-type support scores, each in [0,1], scored only from evidence types actually present in this retrieval (0.0 when a type is absent).",
                "properties": {
                    "literature": {"type": "number", "minimum": 0, "maximum": 1},
                    "protein_evidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "clinical_evidence": {"type": "number", "minimum": 0, "maximum": 1},
                    "llm_rating": {"type": "number", "minimum": 0, "maximum": 1},
                },
                "required": [
                    "literature",
                    "protein_evidence",
                    "clinical_evidence",
                    "llm_rating",
                ],
            },
        },
        "required": [
            "conclusion",
            "verdict",
            "confidence",
            "confidence_rationale",
            "cited_pmids",
            "signal_breakdown",
        ],
    },
}

SIGNAL_KEYS = ("literature", "protein_evidence", "clinical_evidence", "llm_rating")


def _breakdown_problems(resolution: dict) -> list[str]:
    """Return schema violations in resolution's signal_breakdown, empty if
    valid. Code-enforced like citation integrity, because the API does not
    guarantee minimum/maximum are honored in tool output."""
    breakdown = resolution.get("signal_breakdown")
    if not isinstance(breakdown, dict):
        return ["signal_breakdown missing or not an object"]
    problems = []
    for key in SIGNAL_KEYS:
        value = breakdown.get(key)
        if not isinstance(value, (int, float)) or not 0 <= value <= 1:
            problems.append(f"{key}={value!r} is not a number in [0,1]")
    return problems


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
    breakdown_problems = _breakdown_problems(resolution)
    if bad or breakdown_problems:
        # Same code-enforced integrity as synthesizer.py's citation check: one
        # corrective retry, then fail loudly rather than persist an
        # unauditable "conclude" row.
        correction = "\n\nCORRECTION:"
        if bad:
            correction += (
                f" cited_pmids {bad} are not PMIDs from the retrieved evidence "
                f"above. Valid PMIDs are {sorted(valid_pmids)}. Resubmit citing only those."
            )
        if breakdown_problems:
            correction += (
                f" signal_breakdown is invalid: {'; '.join(breakdown_problems)}. "
                f"Every signal must be a number in [0,1]."
            )
        resolution = call_tool(
            llm_client,
            MODEL,
            tool_name="resolve_claim",
            tool_schema=RESOLVE_CLAIM_TOOL["input_schema"],
            prompt=prompt + correction,
        )
        bad = [p for p in resolution["cited_pmids"] if p not in valid_pmids]
        breakdown_problems = _breakdown_problems(resolution)
        if bad:
            raise RuntimeError(
                f"single_call cited PMIDs {bad} not present in this call's retrieval "
                f"for debate {debate_id} after a corrective retry — refusing to persist "
                f"an unauditable confidence."
            )
        if breakdown_problems:
            raise RuntimeError(
                f"single_call returned an invalid signal_breakdown for debate "
                f"{debate_id} after a corrective retry ({'; '.join(breakdown_problems)}) "
                f"— refusing to persist an unauditable confidence."
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
        "signal_breakdown": resolution["signal_breakdown"],
        "driving_provenance_ids": driving_provenance_ids,
        "papers": papers,
    }
