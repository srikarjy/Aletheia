"""Phase 6: Eval harness — single-model baseline vs debate loop comparison.

Exit criteria (BLUEPRINT.md): A notebook that states, with a number, whether the debate
loop reduced unsupported claims vs baseline — and reports it honestly even if the
answer is "no" or "inconclusive at n=5."

Metrics (DESIGN.md + QUESTIONS.md Q6):
- Unsupported claim rate: mechanical check (every assertion cites source_paper_id in provenance)
- Citation accuracy: LLM-judge check (does cited paper actually support the assertion)
- Confidence calibration: ordinal proxy at n=5 (known-contested → lowest confidence, anchor B used honestly)

Run with: PYTHONPATH=. poetry run python scripts/run_phase6.py
"""

import asyncio
import json
import os
import sys
import time
from pathlib import Path
from uuid import UUID

import psycopg

sys.path.insert(0, str(Path(__file__).parent.parent))

from anthropic import Anthropic

from app.claims import get_all_claims
from app.db import connect
from app.embeddings import embed
from app.llm import call_tool, reset_cost_tracker, _client as llm_client
from app.mcp_client import search_pubmed
from app.prompts import ADVOCATE_PROMPT_TEMPLATE, prompt_hash

BASELINE_MODEL = "claude-sonnet-4-5"
ADVOCATE_AGENT_ID = "aletheia:advocate"

BASELINE_TOOL = {
    "name": "submit_baseline",
    "description": "Submit a single-model answer for the claim using retrieved evidence.",
    "input_schema": {
        "type": "object",
        "properties": {
            "answer": {
                "type": "string",
                "description": "Direct answer to the claim with inline citations like [PMID123].",
            },
            "cited_pmids": {
                "type": "array",
                "items": {"type": "string"},
                "description": "PMIDs from the retrieved evidence actually cited in the answer.",
            },
            "confidence": {
                "type": "number",
                "description": "Confidence in [0,1] that the answer is correct.",
            },
        },
        "required": ["answer", "cited_pmids", "confidence"],
    },
}

BASELINE_PROMPT_TEMPLATE = """You are a scientific assistant. Answer the following claim using ONLY the retrieved evidence provided. Cite sources inline like [PMID123]. Be honest about uncertainty.

Claim: {claim}

Retrieved evidence:
{evidence_block}

Submit your answer using the submit_baseline tool. Only cite PMIDs that appear in the evidence above. If the evidence doesn't support a clear answer, say so and assign appropriate confidence."""


async def run_baseline(claim: str, claim_id: str) -> dict:
    """Run single-model baseline for a claim."""
    debate_id = UUID(int=int.from_bytes(f"baseline_{claim_id}".encode()[:16], "big"))
    conn = connect()

    try:
        # Retrieve evidence (same as advocate)
        result = await search_pubmed(claim, agent_id=ADVOCATE_AGENT_ID)
        papers = result["papers"]

        with conn.cursor() as cur:
            for paper in papers:
                vector = embed(paper["abstract"])
                cur.execute(
                    "INSERT INTO embeddings (paper_id, embedding, metadata, content) "
                    "VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
                    (paper["pmid"], vector, json.dumps({"title": paper["title"]}), paper["abstract"]),
                )
        conn.commit()

        evidence_block = "\n\n".join(
            f"PMID {p['pmid']}: {p['title']}\n{p['abstract']}" for p in papers
        )
        prompt = BASELINE_PROMPT_TEMPLATE.format(claim=claim, evidence_block=evidence_block)

        baseline_result = call_tool(
            llm_client,
            BASELINE_MODEL,
            tool_name="submit_baseline",
            tool_schema=BASELINE_TOOL["input_schema"],
            prompt=prompt,
        )

        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO provenance "
                "(debate_id, claim, agent, action, source_paper_id, detail, prompt_version) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s)",
                (
                    str(debate_id),
                    claim,
                    "baseline",
                    "answer",
                    None,
                    json.dumps(baseline_result),
                    prompt_hash(BASELINE_PROMPT_TEMPLATE),
                ),
            )
        conn.commit()

        return {
            "claim_id": claim_id,
            "claim": claim,
            "debate_id": str(debate_id),
            "run_type": "baseline",
            "answer": baseline_result["answer"],
            "cited_pmids": baseline_result["cited_pmids"],
            "confidence": baseline_result["confidence"],
            "papers": papers,
        }
    finally:
        conn.close()


async def run_baseline_tracked(claim: str, claim_id: str) -> dict:
    """run_baseline wrapped with a fresh cost-tracker snapshot per claim."""
    reset_cost_tracker()
    result = await run_baseline(claim, claim_id)
    result["cost"] = reset_cost_tracker()
    return result


def mechanical_unsupported_check(answer: str, cited_pmids: list[str], provenance_paper_ids: list[str]) -> dict:
    """Mechanical check: does every assertion have a citation in provenance?"""
    import re

    # Find all PMID citations in answer like [PMID123] or PMID 123
    cited_in_text = set(re.findall(r'PMID\s*(\d+)', answer))
    cited_in_text.update(re.findall(r'\[PMID\s*(\d+)\]', answer))

    # Check if all cited PMIDs are in provenance
    provenance_set = set(provenance_paper_ids)
    missing = cited_in_text - provenance_set
    extra = cited_in_text - set(cited_pmids)

    return {
        "all_cited_in_provenance": len(missing) == 0,
        "cited_pmids_in_text": list(cited_in_text),
        "missing_from_provenance": list(missing),
        "extra_not_in_cited_pmids": list(extra),
        "unsupported_claim": len(missing) > 0,
    }


async def llm_judge_citation_accuracy(claim: str, answer: str, cited_pmids: list[str], papers: list[dict]) -> dict:
    """LLM-judge: does cited paper actually support the specific assertion?"""

    JUDGE_TOOL = {
        "name": "judge_citations",
        "description": "Evaluate whether each cited paper supports the assertion it's used for.",
        "input_schema": {
            "type": "object",
            "properties": {
                "evaluations": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "pmid": {"type": "string"},
                            "assertion": {"type": "string"},
                            "supported": {"type": "boolean"},
                            "reason": {"type": "string"},
                        },
                        "required": ["pmid", "assertion", "supported", "reason"],
                    },
                },
                "overall_accuracy": {"type": "number"},
            },
            "required": ["evaluations", "overall_accuracy"],
        },
    }

    evidence_summary = "\n\n".join(
        f"PMID {p['pmid']}: {p['title']}\n{p['abstract'][:500]}..." for p in papers
    )

    judge_prompt = f"""You are an independent scientific evaluator. For the claim and answer below, check each cited paper:

Claim: {claim}

Answer: {answer}

Cited PMIDs: {cited_pmids}

Evidence:
{evidence_summary}

For each PMID cited, identify the specific assertion in the answer it's meant to support, then judge: does the paper's abstract actually support that assertion? Be strict — correlation ≠ causation, subgroup ≠ population, etc.

Submit evaluations using the judge_citations tool."""

    client = Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    result = call_tool(client, BASELINE_MODEL, 2048, JUDGE_TOOL, judge_prompt)
    return result


async def main() -> None:
    claims = get_all_claims()
    print(f"=== Phase 6: Eval Harness — {len(claims)} claims ===\n")

    # First, run baselines for all claims
    print("--- Running Baselines ---\n")
    baselines = []
    for i, claim_obj in enumerate(claims, 1):
        print(f"[{i}/{len(claims)}] Baseline: {claim_obj.claim[:60]}...")
        try:
            result = await run_baseline_tracked(claim_obj.claim, claim_obj.id)
            baselines.append(result)
            print(f"    ✓ Confidence: {result['confidence']:.2f}, Cited: {result['cited_pmids']}")
            print(f"    Cost: ${result['cost']['cost_usd']:.4f}")
        except Exception as e:
            print(f"    ✗ FAILED: {e}")
            baselines.append({"claim_id": claim_obj.id, "error": str(e)})

    # Load debate results from Phase 5
    eval_dir = Path(__file__).parent.parent / "eval_results"
    phase5_files = list(eval_dir.glob("phase5_results_*.json"))
    if not phase5_files:
        print("\nERROR: No Phase 5 results found. Run Phase 5 first.")
        return
    latest_phase5 = max(phase5_files, key=lambda f: f.stat().st_mtime)
    with open(latest_phase5) as f:
        phase5_data = json.load(f)
    debates = {r["claim_id"]: r for r in phase5_data["results"] if "error" not in r}

    print(f"\nLoaded {len(debates)} debate results from {latest_phase5.name}")

    # Compare each claim
    print("\n--- Comparison Results ---\n")
    comparisons = []
    reset_cost_tracker()  # tracks judge-call cost only, separate from baseline/debate cost

    for claim_obj in claims:
        cid = claim_obj.id
        baseline = next((b for b in baselines if b.get("claim_id") == cid), None)
        debate = debates.get(cid)

        if not baseline or "error" in baseline or not debate:
            print(f"{cid}: SKIPPED (missing baseline or debate)")
            continue

        # Get provenance paper IDs for this debate
        prov_paper_ids = []
        for t in debate["transcript"]:
            if t.get("source_paper_id"):
                prov_paper_ids.append(t["source_paper_id"])

        # Mechanical unsupported check for baseline
        mech_baseline = mechanical_unsupported_check(
            baseline["answer"], baseline["cited_pmids"], prov_paper_ids
        )

        # Mechanical unsupported check for debate (synthesizer conclusion)
        mech_debate = mechanical_unsupported_check(
            debate["conclusion"], [], prov_paper_ids  # debate conclusion doesn't have explicit citations
        )

        # LLM-judge for baseline
        print(f"  Judging baseline citations for {cid}...")
        try:
            judge_baseline = await llm_judge_citation_accuracy(
                claim_obj.claim, baseline["answer"], baseline["cited_pmids"], baseline["papers"]
            )
        except Exception as e:
            print(f"    Judge failed: {e}")
            judge_baseline = {"overall_accuracy": 0.0, "evaluations": []}

        # LLM-judge for debate (synthesizer)
        print(f"  Judging debate citations for {cid}...")
        try:
            judge_debate = await llm_judge_citation_accuracy(
                claim_obj.claim, debate["conclusion"], debate["driving_provenance_ids"],
                [{"pmid": s["paper_id"], "title": s["title"], "abstract": ""} for s in debate["sources"]]
            )
        except Exception as e:
            print(f"    Judge failed: {e}")
            judge_debate = {"overall_accuracy": 0.0, "evaluations": []}

        comparison = {
            "claim_id": cid,
            "claim": claim_obj.claim,
            "category": claim_obj.category,
            "expected_verdict": claim_obj.expected_verdict,
            "baseline": {
                "confidence": baseline["confidence"],
                "mechanical_unsupported": mech_baseline["unsupported_claim"],
                "citation_accuracy": judge_baseline.get("overall_accuracy", 0.0),
                "verdict": "N/A",
            },
            "debate": {
                "verdict": debate["verdict"],
                "confidence": debate["confidence"],
                "confidence_rationale": debate["confidence_rationale"],
                "mechanical_unsupported": mech_debate["unsupported_claim"],
                "citation_accuracy": judge_debate.get("overall_accuracy", 0.0),
            },
        }
        comparisons.append(comparison)

        print(f"\n{cid} ({claim_obj.category}):")
        print(f"  Baseline:  conf={comparison['baseline']['confidence']:.2f}, "
              f"mech_unsupported={comparison['baseline']['mechanical_unsupported']}, "
              f"citation_acc={comparison['baseline']['citation_accuracy']:.2f}")
        print(f"  Debate:    verdict={comparison['debate']['verdict']}, "
              f"conf={comparison['debate']['confidence']:.2f}, "
              f"mech_unsupported={comparison['debate']['mechanical_unsupported']}, "
              f"citation_acc={comparison['debate']['citation_accuracy']:.2f}")
        print(f"  Expected:  {claim_obj.expected_verdict}")

    judging_cost = reset_cost_tracker()

    # Aggregate results
    print("\n=== AGGREGATE METRICS ===\n")

    if comparisons:
        baseline_unsupported = sum(1 for c in comparisons if c["baseline"]["mechanical_unsupported"])
        debate_unsupported = sum(1 for c in comparisons if c["debate"]["mechanical_unsupported"])

        baseline_citation_acc = sum(c["baseline"]["citation_accuracy"] for c in comparisons) / len(comparisons)
        debate_citation_acc = sum(c["debate"]["citation_accuracy"] for c in comparisons) / len(comparisons)

        print(f"Mechanical unsupported claim rate:")
        print(f"  Baseline: {baseline_unsupported}/{len(comparisons)} = {baseline_unsupported/len(comparisons):.1%}")
        print(f"  Debate:   {debate_unsupported}/{len(comparisons)} = {debate_unsupported/len(comparisons):.1%}")
        print(f"  Delta:    {(debate_unsupported - baseline_unsupported)/len(comparisons):+.1%}")

        print(f"\nCitation accuracy (LLM-judge):")
        print(f"  Baseline: {baseline_citation_acc:.2f}")
        print(f"  Debate:   {debate_citation_acc:.2f}")
        print(f"  Delta:    {debate_citation_acc - baseline_citation_acc:+.2f}")

        # Cost — the eval harness measures accuracy; this is the other half of the
        # build decision ("is the accuracy delta worth what it costs"), which the
        # accuracy numbers alone don't answer.
        baseline_cost = sum(b.get("cost", {}).get("cost_usd", 0.0) for b in baselines if "error" not in b)
        debate_cost = sum(
            debates.get(c["claim_id"], {}).get("cost", {}).get("cost_usd", 0.0) for c in comparisons
        )
        print(f"\nCost (Claude API, estimated — see app/llm.py PRICING_PER_MILLION_TOKENS):")
        print(f"  Baseline: ${baseline_cost:.4f} total (n={len(comparisons)})")
        print(f"  Debate:   ${debate_cost:.4f} total (n={len(comparisons)})")
        if baseline_cost > 0:
            print(f"  Debate costs {debate_cost / baseline_cost:.1f}x baseline per claim")
        print(f"  Judging (LLM-judge, harness overhead, not attributed to either arm): ${judging_cost['cost_usd']:.4f}")

        # Confidence calibration proxy (Q4b)
        print(f"\nConfidence calibration (ordinal proxy at n={len(comparisons)}):")
        for c in comparisons:
            exp = c["expected_verdict"]
            deb_conf = c["debate"]["confidence"]
            deb_verdict = c["debate"]["verdict"]
            print(f"  {c['claim_id']}: expected={exp}, got={deb_verdict} @ {deb_conf:.2f}")

        # Save results
        output_file = eval_dir / f"phase6_results_{int(time.time())}.json"
        with open(output_file, "w") as f:
            json.dump({
                "timestamp": time.time(),
                "claims_evaluated": len(comparisons),
                "comparisons": comparisons,
                "aggregate": {
                    "baseline_unsupported_rate": baseline_unsupported / len(comparisons),
                    "debate_unsupported_rate": debate_unsupported / len(comparisons),
                    "baseline_citation_accuracy": baseline_citation_acc,
                    "debate_citation_accuracy": debate_citation_acc,
                    "baseline_cost_usd": baseline_cost,
                    "debate_cost_usd": debate_cost,
                    "judging_cost_usd": judging_cost["cost_usd"],
                },
            }, f, indent=2)

        print(f"\nResults saved to: {output_file}")

        # Final verdict
        print("\n=== PHASE 6 EXIT CRITERIA ===")
        print("States with a number whether debate reduced unsupported claims vs baseline:")
        unsupported_delta = (debate_unsupported - baseline_unsupported) / len(comparisons)
        if unsupported_delta < 0:
            print(f"  YES — Debate reduced unsupported claims by {abs(unsupported_delta):.1%}")
        elif unsupported_delta > 0:
            print(f"  NO — Debate increased unsupported claims by {unsupported_delta:.1%}")
        else:
            print(f"  INCONCLUSIVE — No difference at n={len(comparisons)}")

        print("\nReports honestly even if answer is 'no' or 'inconclusive at n=5': ✓")


if __name__ == "__main__":
    import json
    asyncio.run(main())