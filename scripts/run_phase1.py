"""Proves Phase 1's exit criteria for real (BLUEPRINT.md):

"Given one fixed claim, the system returns real PubMed IDs with real
titles/abstracts, and rows exist in `embeddings` you can query back by similarity."

Run with: poetry run python scripts/run_phase1.py
"""

import asyncio
from uuid import uuid4

from app.db import connect
from app.embeddings import embed
from app.retrieval import retrieve_and_persist

CLAIM = "BRCA1 mutations increase pancreatic cancer risk"


async def main():
    conn = connect()
    debate_id = uuid4()

    papers = await retrieve_and_persist(conn, CLAIM, debate_id)

    print(f"--- retrieved {len(papers)} real papers for claim: {CLAIM!r} ---")
    for paper in papers:
        print(f"  pmid={paper['pmid']} retrieval_id={paper['retrieval_id']}")
        print(f"  title={paper['title'][:80]}")

    print("\n--- similarity query against embeddings table ---")
    query_vector = embed(CLAIM)
    with conn.cursor() as cur:
        cur.execute(
            "SELECT paper_id, content, embedding <=> %s::vector AS distance "
            "FROM embeddings ORDER BY distance LIMIT 3",
            (query_vector,),
        )
        for paper_id, content, distance in cur.fetchall():
            print(f"  paper_id={paper_id} distance={distance:.4f} content={content[:80]!r}")

    print("\n--- provenance rows for this debate_id ---")
    with conn.cursor() as cur:
        cur.execute(
            "SELECT agent, action, source_paper_id, retrieval_id FROM provenance "
            "WHERE debate_id = %s",
            (str(debate_id),),
        )
        for row in cur.fetchall():
            print(f"  {row}")

    conn.close()


if __name__ == "__main__":
    asyncio.run(main())
