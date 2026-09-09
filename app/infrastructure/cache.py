"""Small, bounded L1 cache used in front of the Postgres runtime store."""

from __future__ import annotations

import time
from collections import OrderedDict
from threading import RLock
from typing import Generic, Iterator, MutableMapping, TypeVar

K = TypeVar("K")
V = TypeVar("V")


class TTLCache(MutableMapping[K, V], Generic[K, V]):
    """Thread-safe LRU + TTL mapping with lightweight operational metrics."""

    def __init__(self, max_size: int = 512, ttl_seconds: int = 3600) -> None:
        self.max_size = max(1, max_size)
        self.ttl_seconds = max(1, ttl_seconds)
        self._items: OrderedDict[K, tuple[float, V]] = OrderedDict()
        self._lock = RLock()
        self.hits = 0
        self.misses = 0
        self.evictions = 0

    def __getitem__(self, key: K) -> V:
        with self._lock:
            item = self._items.get(key)
            if item is None:
                self.misses += 1
                raise KeyError(key)
            expires_at, value = item
            if expires_at <= time.time():
                del self._items[key]
                self.misses += 1
                self.evictions += 1
                raise KeyError(key)
            self._items.move_to_end(key)
            self.hits += 1
            return value

    def __setitem__(self, key: K, value: V) -> None:
        with self._lock:
            self._items[key] = (time.time() + self.ttl_seconds, value)
            self._items.move_to_end(key)
            while len(self._items) > self.max_size:
                self._items.popitem(last=False)
                self.evictions += 1

    def __delitem__(self, key: K) -> None:
        with self._lock:
            del self._items[key]

    def __iter__(self) -> Iterator[K]:
        with self._lock:
            self._prune()
            return iter(list(self._items.keys()))

    def __len__(self) -> int:
        with self._lock:
            self._prune()
            return len(self._items)

    def _prune(self) -> int:
        now = time.time()
        expired = [key for key, (expiry, _) in self._items.items() if expiry <= now]
        for key in expired:
            del self._items[key]
        self.evictions += len(expired)
        return len(expired)

    def stats(self) -> dict[str, int | float]:
        with self._lock:
            self._prune()
            total = self.hits + self.misses
            return {
                "size": len(self._items),
                "max_size": self.max_size,
                "ttl_seconds": self.ttl_seconds,
                "hits": self.hits,
                "misses": self.misses,
                "hit_rate": round(self.hits / total, 3) if total else 0.0,
                "evictions": self.evictions,
            }

    def clear(self) -> None:
        with self._lock:
            self._items.clear()
