"""Phase 5: Run the full debate pipeline over all 5 curated claims.

Exit criteria (BLUEPRINT.md): All 5 claims produce a debate transcript + conclusion +
provenance, saved and inspectable, with zero manual intervention between claims.

Run with: PYTHONPATH=. poetry run python scripts/run_phase5.py
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

from app.agents.advocate import advocate
from app.agents.skeptic import skeptic
from app.agents.synthesizer import synthesizer
from app.claims import get_all_claims
from app.db import connect
from app.llm import reset_cost_tracker


async def run_single_debate(claim: str, claim_id: str) -> dict:
    """Run one complete debate for a claim, returning structured results."""
    debate_id = UUID(int=int.from_bytes(claim_id.encode()[:16], "big"))
    conn = connect()
    try:
        advocate_result = await advocate(conn, claim, debate_id)
        await skeptic(conn, debate_id, advocate_result)
        conclusion = await synthesizer(conn, debate_id, claim)

        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, agent, action, source_paper_id, detail, prompt_version "
                "FROM provenance WHERE debate_id = %s ORDER BY id",
                (str(debate_id),),
            )
            prov_rows = cur.fetchall()

        transcript = [
            {
                "id": r[0],
                "agent": r[1],
                "action": r[2],
                "source_paper_id": r[3],
                "detail": r[4] if r[4] is not None else {},
                "prompt_version": r[5],
            }
            for r in prov_rows
        ]

        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT source_paper_id FROM provenance "
                "WHERE debate_id = %s AND source_paper_id IS NOT NULL",
                (str(debate_id),),
            )
            paper_ids = [r[0] for r in cur.fetchall()]

        sources = []
        with conn.cursor() as cur:
            for pid in paper_ids:
                cur.execute(
                    "SELECT paper_id, metadata FROM embeddings WHERE paper_id = %s LIMIT 1",
                    (pid,),
                )
                row = cur.fetchone()
                if row:
                    meta = row[1] if row[1] else {}
                    title = meta.get("title", "Unknown") if isinstance(meta, dict) else "Unknown"
                    sources.append({"paper_id": row[0], "title": title, "used_by": ["advocate", "skeptic"]})

        return {
            "claim_id": claim_id,
            "claim": claim,
            "debate_id": str(debate_id),
            "verdict": conclusion["verdict"],
            "confidence": conclusion["confidence"],
            "confidence_rationale": conclusion["confidence_rationale"],
            "driving_provenance_ids": conclusion["driving_provenance_ids"],
            "conclusion": conclusion["conclusion"],
            "transcript": transcript,
            "sources": sources,
            "num_provenance_rows": len(prov_rows),
        }
    finally:
        conn.close()


async def main() -> None:
    claims = get_all_claims()
    print(f"=== Phase 5: Running {len(claims)} curated claims ===\n")

    results = []
    total_start = time.monotonic()

    for i, claim_obj in enumerate(claims, 1):
        print(f"[{i}/{len(claims)}] {claim_obj.id}: {claim_obj.claim}")
        print(f"    Category: {claim_obj.category}, Expected: {claim_obj.expected_verdict or 'N/A'}")
        print(f"    Rationale: {claim_obj.rationale[:100]}...")

        reset_cost_tracker()  # per-claim cost, not a running total across claims
        start = time.monotonic()
        try:
            result = await run_single_debate(claim_obj.claim, claim_obj.id)
            latency = time.monotonic() - start
            cost = reset_cost_tracker()
            result["latency_seconds"] = latency
            result["cost"] = cost
            result["expected_verdict"] = claim_obj.expected_verdict
            result["category"] = claim_obj.category
            results.append(result)

            print(f"    ✓ Completed in {latency:.1f}s")
            print(f"    Verdict: {result['verdict']}, Confidence: {result['confidence']:.2f}")
            print(f"    Provenance rows: {result['num_provenance_rows']}, Sources: {len(result['sources'])}")
            print(f"    Cost: ${cost['cost_usd']:.4f} ({cost['input_tokens']}+{cost['output_tokens']} tokens, {cost['calls']} calls)")

        except Exception as e:
            latency = time.monotonic() - start
            cost = reset_cost_tracker()
            print(f"    ✗ FAILED after {latency:.1f}s: {e}")
            results.append({
                "claim_id": claim_obj.id,
                "claim": claim_obj.claim,
                "error": str(e),
                "latency_seconds": latency,
                "cost": cost,
                "expected_verdict": claim_obj.expected_verdict,
                "category": claim_obj.category,
            })

        print()

    total_latency = time.monotonic() - total_start
    print(f"=== Phase 5 Complete: {total_latency:.1f}s total ===\n")

    # Save results
    output_dir = Path(__file__).parent.parent / "eval_results"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"phase5_results_{int(total_start)}.json"

    with open(output_file, "w") as f:
        json.dump({
            "timestamp": total_start,
            "total_latency_seconds": total_latency,
            "claims_run": len(claims),
            "results": results,
        }, f, indent=2)

    print(f"Results saved to: {output_file}")

    # Summary
    successful = [r for r in results if "error" not in r]
    failed = [r for r in results if "error" in r]

    print(f"\nSummary: {len(successful)}/{len(claims)} successful, {len(failed)} failed")
    for r in successful:
        match = "✓" if r.get("expected_verdict") == r.get("verdict") else "✗"
        print(f"  {match} {r['claim_id']}: got {r['verdict']} (expected {r.get('expected_verdict', 'N/A')}), conf={r['confidence']:.2f}")

    total_cost = sum(r.get("cost", {}).get("cost_usd", 0.0) for r in results)
    total_calls = sum(r.get("cost", {}).get("calls", 0) for r in results)
    print(f"\nTotal cost: ${total_cost:.4f} across {total_calls} Claude calls ({len(results)} claims)")

    if failed:
        print("\nFailures:")
        for r in failed:
            print(f"  ✗ {r['claim_id']}: {r['error']}")

    # Exit criteria check
    all_success = len(successful) == len(claims) and all(r.get("num_provenance_rows", 0) > 0 for r in successful)
    print(f"\nPHASE 5 EXIT CRITERIA: {'PASS' if all_success else 'FAIL'}")
    if not all_success:
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())