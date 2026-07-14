"""Proves Phase 3's exit criteria for real (BLUEPRINT.md):

"For 1 claim, the debate transcript shows at least one concrete challenge the
skeptic raised against the advocate's case, with a provenance row proving it
happened."

Run with: PYTHONPATH=. poetry run python scripts/run_phase3.py
"""

import asyncio
import json
from uuid import uuid4

from app.agents.advocate import advocate
from app.agents.skeptic import skeptic
from app.db import connect

CLAIM = "BRCA1 mutations increase pancreatic cancer risk"


async def main():
    conn = connect()
    debate_id = uuid4()

    advocate_result = await advocate(conn, CLAIM, debate_id)
    print(f"--- advocate's case ---")
    print(json.dumps(advocate_result["case"], indent=2))

    critique = await skeptic(conn, debate_id, advocate_result)
    print(f"\n--- skeptic's critique ---")
    print(json.dumps(critique, indent=2))

    print("\n--- full debate transcript, reconstructed from provenance, in order ---")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT agent, action, source_paper_id, detail, timestamp "
            "FROM provenance WHERE debate_id = %s ORDER BY timestamp",
            (str(debate_id),),
        )
        for agent, action, source_paper_id, detail, ts in cur.fetchall():
            print(f"  [{ts}] agent={agent} action={action} source_paper_id={source_paper_id}")
            if action in ("critique", "assess"):
                print(f"      detail={detail}")

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
