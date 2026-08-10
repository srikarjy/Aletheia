"""OpenAI embeddings with caching. Model choice reasoning: QUESTIONS.md — 1536-dim
text-embedding-3-small matches the already-migrated schema, no local inference infra,
revisit only if Phase 6's eval harness measures retrieval quality as an actual bottleneck.

Supports MOCK_EMBEDDINGS=true for demo/deployment without OpenAI dependency.
"""

import hashlib
import os
import random

from openai import OpenAI

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536

_client: OpenAI | None = None
if os.environ.get("MOCK_EMBEDDINGS", "").lower() != "true":
    _client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))

_embedding_cache: dict[str, list[float]] = {}


def _cache_key(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()[:32]


def _mock_embedding(text: str) -> list[float]:
    """Generate deterministic mock embedding based on text hash."""
    random.seed(hashlib.md5(text.encode()).hexdigest(), version=2)
    return [random.uniform(-1, 1) for _ in range(EMBEDDING_DIM)]


def embed(text: str) -> list[float]:
    key = _cache_key(text)
    if key in _embedding_cache:
        return _embedding_cache[key]
    
    if _client is None:
        embedding = _mock_embedding(text)
    else:
        response = _client.embeddings.create(model=EMBEDDING_MODEL, input=text)
        embedding = response.data[0].embedding
    
    _embedding_cache[key] = embedding
    return embedding


def clear_embedding_cache() -> int:
    count = len(_embedding_cache)
    _embedding_cache.clear()
    return count


def get_embedding_cache_stats() -> dict:
    return {"size": len(_embedding_cache)}
