import time

import pytest

from app.infrastructure.cache import TTLCache
from app.infrastructure.state import RuntimeState


def test_ttl_cache_is_bounded_and_tracks_hits():
    cache = TTLCache[str, int](max_size=2, ttl_seconds=60)
    cache["a"] = 1
    cache["b"] = 2
    assert cache["a"] == 1
    cache["c"] = 3
    assert "b" not in cache
    assert cache.stats()["hits"] >= 1
    assert cache.stats()["evictions"] == 1


def test_ttl_cache_expires_entries(monkeypatch):
    now = 1000.0
    monkeypatch.setattr(time, "time", lambda: now)
    cache = TTLCache[str, int](max_size=2, ttl_seconds=5)
    cache["a"] = 1
    now = 1006.0
    with pytest.raises(KeyError):
        _ = cache["a"]


def test_runtime_memory_falls_back_without_postgres(monkeypatch):
    state = RuntimeState()
    monkeypatch.setattr(state, "ensure_schema", lambda: False)
    payload = {
        "debate_id": "12345678-1234-5678-1234-567812345678",
        "claim": "A claim",
        "verdict": "unresolved",
        "confidence": 0.5,
    }
    state.remember(payload, "single_call", owner="alice")
    assert state.get_memory(payload["debate_id"], owner="alice") == payload
    assert state.list_memories(owner="alice")[0]["claim"] == "A claim"
