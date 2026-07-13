"""OpenAI embeddings. Model choice reasoning: QUESTIONS.md — 1536-dim text-embedding-3-small
matches the already-migrated schema, no local inference infra, revisit only if Phase 6's
eval harness measures retrieval quality as an actual bottleneck.
"""

import os

from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"

_client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


def embed(text: str) -> list[float]:
    response = _client.embeddings.create(model=EMBEDDING_MODEL, input=text)
    return response.data[0].embedding
