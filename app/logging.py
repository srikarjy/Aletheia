"""Structured logging with request ID correlation."""

import contextvars
import logging
import sys
import uuid
from typing import Any

import structlog

# Context variable to hold request ID across async boundaries
request_id_var: contextvars.ContextVar[str | None] = contextvars.ContextVar("request_id", default=None)


def get_request_id() -> str:
    """Get current request ID, generating one if not set."""
    rid = request_id_var.get()
    if rid is None:
        rid = str(uuid.uuid4())[:8]
        request_id_var.set(rid)
    return rid


def set_request_id(rid: str | None = None) -> str:
    """Set request ID for current context."""
    if rid is None:
        rid = str(uuid.uuid4())[:8]
    request_id_var.set(rid)
    return rid


def clear_request_id() -> None:
    """Clear request ID from current context."""
    request_id_var.set(None)


class RequestIDProcessor:
    """structlog processor that adds request_id to all log entries."""
    
    def __call__(self, logger: Any, method_name: str, event_dict: dict) -> dict:
        rid = request_id_var.get()
        if rid:
            event_dict["request_id"] = rid
        return event_dict


def configure_logging(level: str = "INFO", json_output: bool = False) -> None:
    """Configure structlog with request ID correlation."""
    shared_processors = [
        structlog.contextvars.merge_contextvars,
        RequestIDProcessor(),
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.dev.set_exc_info,
    ]
    
    if json_output:
        shared_processors.append(structlog.processors.JSONRenderer())
    else:
        shared_processors.append(structlog.dev.ConsoleRenderer(colors=True))
    
    structlog.configure(
        processors=shared_processors,
        wrapper_class=structlog.make_filtering_bound_logger(getattr(logging, level.upper())),
        context_class=dict,
        logger_factory=structlog.PrintLoggerFactory(file=sys.stdout),
        cache_logger_on_first_use=True,
    )
    
    # Also configure standard library logging
    logging.basicConfig(
        format="%(message)s",
        stream=sys.stdout,
        level=getattr(logging, level.upper()),
    )


def get_logger(name: str | None = None) -> structlog.BoundLogger:
    """Get a structlog logger instance."""
    return structlog.get_logger(name)


# Middleware for FastAPI to set request ID
async def request_id_middleware(request: "Request", call_next: "Callable") -> "Response":
    """FastAPI middleware to set request ID for each request."""
    from starlette.requests import Request
    from starlette.responses import Response
    
    rid = request.headers.get("X-Request-ID") or str(uuid.uuid4())[:8]
    token = request_id_var.set(rid)
    try:
        response = await call_next(request)
        response.headers["X-Request-ID"] = rid
        return response
    finally:
        request_id_var.reset(token)