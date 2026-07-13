"""Proves Phase 2's exit criteria for real (BLUEPRINT.md):

"For 1 claim, you can query `provenance` and reconstruct every step the advocate
took, in order, each linked to a real `source_paper_id`."

Run with: PYTHONPATH=. poetry run python scripts/run_phase2.py
"""

import asyncio
import json
from uuid import uuid4

from app.agents.advocate import advocate
from app.db import connect

CLAIM = "BRCA1 mutations increase pancreatic cancer risk"


async def main():
    conn = connect()
    debate_id = uuid4()

    result = await advocate(conn, CLAIM, debate_id)

    print(f"--- advocate's case for: {CLAIM!r} ---")
    print(json.dumps(result["case"], indent=2))

    print("\n--- reconstructing every step from provenance, in order ---")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT agent, action, source_paper_id, retrieval_id, prompt_version, timestamp "
            "FROM provenance WHERE debate_id = %s ORDER BY timestamp",
            (str(debate_id),),
        )
        for agent, action, source_paper_id, retrieval_id, prompt_version, ts in cur.fetchall():
            print(
                f"  [{ts}] agent={agent} action={action} "
                f"source_paper_id={source_paper_id} retrieval_id={retrieval_id} "
                f"prompt_version={prompt_version}"
            )

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
