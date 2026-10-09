"""Per-run resource budget (ADR-003 guardrail G5).

A multi-agent run is a loop of model calls, and loops need a hard stop: a runaway
debate, a retry storm, or a stuck workflow should end with a clear error, not a surprise
bill. A Budget caps calls, tokens, estimated dollars and wall-clock seconds for ONE run.

How it is wired: `budget_scope(Budget(...))` sets a context variable; `app.llm.call_tool`
(the single choke point for every model call) calls `begin_call()` before it talks to a
provider and `charge()` after each response. Because it rides a ContextVar, agents and
future LangGraph/CrewAI nodes need no budget argument: any code that calls the gateway
inside the scope is metered. The Budget object is shared by reference, so concurrent
tasks spawned inside the scope (asyncio.gather) all draw from the same pool.

Honest limits:
  - The check runs before a call, the charge after it, so a run can overshoot a cap by
    at most one in-flight call.
  - Dollars use app.llm.PRICING_PER_MILLION_TOKENS; a model missing from that table
    costs 0.0 there, so for such models only the call/token/time caps protect you.
  - Calls are counted per call_tool invocation, not per truncation retry inside it
    (retries are still charged for their tokens).
"""

import os
import threading
import time
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass, field


class BudgetExceeded(RuntimeError):
    """A run hit one of its resource caps and was stopped."""

    def __init__(self, resource: str, used: float, limit: float):
        self.resource, self.used, self.limit = resource, used, limit
        super().__init__(f"run budget exceeded: {resource} {used:g} >= limit {limit:g}")


@dataclass
class Budget:
    max_calls: int = 12
    max_tokens: int = 500_000
    max_usd: float = 2.00
    max_seconds: float = 600.0

    calls: int = 0
    tokens: int = 0
    usd: float = 0.0
    started: float = field(default_factory=time.monotonic)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    @classmethod
    def from_env(cls) -> "Budget":
        """Defaults sized for the 3-agent debate (about 3-5 calls) with headroom."""
        return cls(
            max_calls=int(os.environ.get("BUDGET_MAX_CALLS", "12")),
            max_tokens=int(os.environ.get("BUDGET_MAX_TOKENS", "500000")),
            max_usd=float(os.environ.get("BUDGET_MAX_USD", "2.00")),
            max_seconds=float(os.environ.get("BUDGET_MAX_SECONDS", "600")),
        )

    @property
    def elapsed(self) -> float:
        return time.monotonic() - self.started

    def _check_locked(self) -> None:
        if self.calls >= self.max_calls:
            raise BudgetExceeded("calls", self.calls, self.max_calls)
        if self.tokens >= self.max_tokens:
            raise BudgetExceeded("tokens", self.tokens, self.max_tokens)
        if self.usd >= self.max_usd:
            raise BudgetExceeded("usd", self.usd, self.max_usd)
        if self.elapsed >= self.max_seconds:
            raise BudgetExceeded("seconds", self.elapsed, self.max_seconds)

    def check(self) -> None:
        with self._lock:
            self._check_locked()

    def begin_call(self) -> None:
        """Gate a new model call: raise if any cap is already reached, else count it."""
        with self._lock:
            self._check_locked()
            self.calls += 1

    def charge(self, input_tokens: int, output_tokens: int, usd: float) -> None:
        with self._lock:
            self.tokens += int(input_tokens) + int(output_tokens)
            self.usd += float(usd)

    def snapshot(self) -> dict:
        with self._lock:
            return {
                "calls": self.calls, "tokens": self.tokens, "usd": round(self.usd, 6),
                "seconds": round(self.elapsed, 3),
                "limits": {"calls": self.max_calls, "tokens": self.max_tokens,
                           "usd": self.max_usd, "seconds": self.max_seconds},
            }


_current: ContextVar[Budget | None] = ContextVar("aletheia_budget", default=None)


@contextmanager
def budget_scope(budget: Budget):
    """Meter every gateway call made inside the block against `budget`."""
    token = _current.set(budget)
    try:
        yield budget
    finally:
        _current.reset(token)


def current_budget() -> Budget | None:
    return _current.get()


# --- hooks called by app.llm ---------------------------------------------------

def begin_call() -> None:
    b = _current.get()
    if b is not None:
        b.begin_call()


def check() -> None:
    b = _current.get()
    if b is not None:
        b.check()


def charge(input_tokens: int, output_tokens: int, usd: float) -> None:
    b = _current.get()
    if b is not None:
        b.charge(input_tokens, output_tokens, usd)
