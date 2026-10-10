"""The shared retrieval boundary (ADR-003, Phase 11).

Every workflow gets papers through a `Retriever`, and every retriever is wrapped in the
injection screen, so there is exactly one place where untrusted text enters the system.
Two implementations:

  LiveRetriever     PubMed through the Biolab MCP client (honours MOCK_RETRIEVAL).
  FixtureRetriever  a fixed in-memory corpus, for the red-team sandbox and for tests.
                    Nothing is sent anywhere, so attack strings stay inside the process.

`use_retriever(r)` swaps the retriever for a block of code through a ContextVar (the same
trick as app.budget), so LangGraph/CrewAI nodes need no retriever argument.
"""

import re
from contextlib import contextmanager
from contextvars import ContextVar
from typing import Protocol

from app.guardrails import Quarantine, screen_papers
from app.mcp_client import search_pubmed


class Retriever(Protocol):
    async def search(self, query: str, *, agent_id: str, max_results: int = 5) -> dict:
        """Return {"query_echo": str, "papers": [{"pmid","retrieval_id","title","abstract"}]}."""


class LiveRetriever:
    async def search(self, query: str, *, agent_id: str, max_results: int = 5) -> dict:
        return await search_pubmed(query, agent_id=agent_id, max_results=max_results)


_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class FixtureRetriever:
    """Ranks a fixed corpus by word overlap with the query. Deterministic."""

    def __init__(self, papers: list[dict]):
        self._papers = [dict(p) for p in papers]

    async def search(self, query: str, *, agent_id: str, max_results: int = 5) -> dict:
        q = _tokens(query)
        scored = sorted(
            ((len(q & _tokens(p["title"] + " " + p["abstract"])), i) for i, p in enumerate(self._papers)),
            key=lambda s: (-s[0], s[1]),
        )
        hits = [dict(self._papers[i]) for score, i in scored if score > 0][:max_results]
        return {"query_echo": query, "papers": hits}


_current: ContextVar[Retriever | None] = ContextVar("aletheia_retriever", default=None)


def current_retriever() -> Retriever:
    return _current.get() or LiveRetriever()


@contextmanager
def use_retriever(retriever: Retriever):
    token = _current.set(retriever)
    try:
        yield retriever
    finally:
        _current.reset(token)


async def screened_search(
    query: str, *, agent_id: str, max_results: int = 5
) -> tuple[list[dict], list[Quarantine]]:
    """Search with the current retriever, then sanitize and quarantine. Returns
    (clean papers, quarantined records). This is the only entry point agents should use."""
    result = await current_retriever().search(query, agent_id=agent_id, max_results=max_results)
    return screen_papers(result["papers"])
