# ADR-001: Hybrid runtime state and provider-neutral LLM gateway

**Status:** Accepted
**Date:** 2026-09-09

## Context

Aletheia's original API stored response cache entries and async jobs in unbounded
module dictionaries. They disappeared on restart, could grow without a limit, and
could not be inspected across API replicas. Agent calls were also tied to Anthropic's
tool-use API even though lower-cost structured-output models are sufficient for many
development and evaluation runs.

## Decision

Use a bounded TTL/LRU cache as the process-local L1 and Postgres as the durable L2.
Persist completed research runs, cache entries, and the async job ledger beside the
existing provenance and pgvector data. Keep in-process background execution for this
single-node prototype, but isolate its state contract so a real worker can replace it.

Put all agent model calls behind `app.llm.call_tool`. Support Anthropic natively and
DeepSeek, Qwen/DashScope, or another OpenAI-compatible endpoint through environment
configuration. Record the selected provider and model inside every persisted LLM
artifact. The application database remains the provenance source of truth.

## Options considered

| Option | Complexity | Durability | Fit now |
|---|---:|---:|---:|
| In-memory dictionaries | Low | None | Poor |
| Redis + separate worker now | High | Configurable | Premature for one node |
| Bounded L1 + Postgres L2 | Medium | Strong | Best |
| LangChain/LangGraph rewrite | High | Unrelated | Poor |

## Consequences

- Repeated claims are fast and cache state survives API restarts.
- Research history and job status have one durable home.
- Deployments can change model cost/quality without changing agent code.
- Background work is not yet horizontally distributed; add a Redis/SQS-backed worker
  only when multiple API replicas or retry/resume guarantees are required.
- LangSmith may be added as a trace exporter, but never replaces first-party provenance.
