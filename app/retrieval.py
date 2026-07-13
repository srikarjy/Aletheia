"""Phase 1: one retrieval call, one claim, no agent loop yet (BLUEPRINT.md Phase 1).

agent="system" (not "advocate") in the provenance rows this writes — Phase 1 explicitly
has no agent loop, so labeling this "advocate" would misrepresent that an agent reasoned
about anything. Phase 2 introduces the real advocate agent and its own provenance rows.
"""

import json
from uuid import UUID

import psycopg

from app.embeddings import embed
from app.mcp_client import search_pubmed

RETRIEVAL_AGENT_ID = "aletheia:phase1-retrieval"


async def retrieve_and_persist(conn: psycopg.Connection, claim: str, debate_id: UUID) -> list[dict]:
    result = await search_pubmed(claim, agent_id=RETRIEVAL_AGENT_ID)
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
                    "system",
                    "retrieve",
                    paper["pmid"],
                    paper["retrieval_id"],
                    json.dumps({"title": paper["title"], "note": "Phase 1, no agent loop"}),
                ),
            )
    conn.commit()
    return papers
