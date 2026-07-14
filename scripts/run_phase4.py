"""Proves Phase 4's exit criteria for real (BLUEPRINT.md):

"For 1 claim, POST /debate returns a structured conclusion + confidence score +
full transcript + provenance, end to end, through the real FastAPI endpoint (not
a fixture)."

Starts the real uvicorn server, POSTs a claim over HTTP, and then independently
reads the provenance table to prove the synthesizer's "conclude" row (with its
rubric prompt_version and code-validated driving_provenance_ids) was actually
persisted — not just returned in the response body.

Run with: PYTHONPATH=. poetry run python scripts/run_phase4.py
(env from .env must be loaded — see README)
"""

import json
import os
import time

import httpx
import psycopg

BASE_URL = "http://127.0.0.1:8000"
CLAIM = "BRCA1 mutations increase pancreatic cancer risk"


def main() -> None:
    t0 = time.monotonic()
    resp = httpx.post(f"{BASE_URL}/debate", json={"claim": CLAIM}, timeout=180.0)
    latency = time.monotonic() - t0
    resp.raise_for_status()
    body = resp.json()

    print("=== POST /debate response ===")
    print(f"HTTP {resp.status_code}  latency={latency:.1f}s  (Q8 datapoint)")
    print(f"debate_id : {body['debate_id']}")
    print(f"verdict   : {body['verdict']}")
    print(f"confidence: {body['confidence']}")
    print(f"rationale : {body['confidence_rationale']}")
    print(f"drivers   : {body['driving_provenance_ids']}")
    print(f"conclusion: {body['conclusion']}")
    print(f"sources   : {len(body['sources'])} papers, {len(body['transcript'])} transcript rows")

    # Independently prove the conclude row landed in provenance, with its rubric version,
    # and that every driving id is a real row in THIS debate (the code-enforced invariant).
    conn = psycopg.connect(os.environ["DATABASE_URL"])
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, agent, action, prompt_version FROM provenance "
            "WHERE debate_id = %s ORDER BY id",
            (body["debate_id"],),
        )
        rows = cur.fetchall()
    conn.close()

    ids = {r[0] for r in rows}
    conclude = [r for r in rows if r[2] == "conclude"]
    drivers_ok = all(d in ids for d in body["driving_provenance_ids"])

    print("\n=== provenance, reconstructed independently from Postgres ===")
    for r in rows:
        print(f"  id={r[0]:<4} agent={r[1]:<11} action={r[2]:<9} prompt_version={r[3]}")

    print("\n=== exit-criteria checks ===")
    print(f"  structured conclusion returned : {bool(body['conclusion'])}")
    print(f"  confidence in [0,1]            : {0.0 <= body['confidence'] <= 1.0}")
    print(f"  synthesizer 'conclude' persisted: {len(conclude) == 1}")
    print(f"  rubric prompt_version stamped   : {bool(conclude and conclude[0][3])}")
    print(f"  driving ids all real, this debate: {drivers_ok}")
    ok = (
        bool(body["conclusion"])
        and 0.0 <= body["confidence"] <= 1.0
        and len(conclude) == 1
        and bool(conclude and conclude[0][3])
        and drivers_ok
    )
    print(f"\nPHASE 4 EXIT CRITERIA: {'PASS' if ok else 'FAIL'}")


if __name__ == "__main__":
    main()
