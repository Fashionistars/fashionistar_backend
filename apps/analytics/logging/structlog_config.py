"""
apps/analytics/logging/structlog_config.py
============================================
Structured JSON logging configuration for analytics modules.

Features:
  - JSON-formatted log output in production
  - Correlation IDs included in every log entry
  - Sensitive fields redacted via _scrub_pii
  - Compatible with ELK/Logstash ingestion

Usage (in settings.py):
    from apps.analytics.logging.structlog_config import configure_structlog
    configure_structlog()
"""

from __future__ import annotations

import logging
import sys
from typing import Any

# Fields to redact from log records
_REDACTED_FIELDS = {
    "ip_address",
    "user_agent",
    "session_id",
    "password",
    "token",
    "api_key",
    "secret",
    "authorization",
}

_REDACTED_VALUE = "***REDACTED***"


def _redact_sensitive_fields(data: dict[str, Any]) -> dict[str, Any]:
    """Redact sensitive fields from a dict."""
    redacted = {}
    for key, value in data.items():
        if key.lower() in _REDACTED_FIELDS:
            redacted[key] = _REDACTED_VALUE
        elif isinstance(value, dict):
            redacted[key] = _redact_sensitive_fields(value)
        else:
            redacted[key] = value
    return redacted


class StructuredJSONFormatter(logging.Formatter):
    """
    JSON log formatter for structured logging.

    Outputs log records as JSON with:
      - timestamp
      - level
      - logger name
      - message
      - correlation_id (if available)
      - extra fields (redacted)
    """

    def format(self, record: logging.LogRecord) -> str:
        import json
        from datetime import datetime

        log_entry = {
            "timestamp": datetime.utcnow().isoformat() + "Z",
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
            "module": record.module,
            "line": record.lineno,
        }

        # Add correlation ID if present
        correlation_id = getattr(record, "correlation_id", None)
        if correlation_id:
            log_entry["correlation_id"] = correlation_id

        # Add request ID if present
        request_id = getattr(record, "request_id", None)
        if request_id:
            log_entry["request_id"] = request_id

        # Add extra fields (redacted)
        extra = {}
        for key, value in record.__dict__.items():
            if key not in {
                "name", "msg", "args", "levelname", "levelno", "pathname",
                "filename", "module", "exc_info", "exc_text", "stack_info",
                "lineno", "funcName", "created", "msecs", "relativeCreated",
                "thread", "threadName", "processName", "process", "message",
                "correlation_id", "request_id",
            }:
                extra[key] = value

        if extra:
            log_entry["extra"] = _redact_sensitive_fields(extra)

        # Add exception info if present
        if record.exc_info:
            log_entry["exception"] = self.formatException(record.exc_info)

        return json.dumps(log_entry, default=str)


def configure_structlog() -> None:
    """
    Configure structured JSON logging for analytics modules.

    Call this from Django settings.py in production.
    """
    # Configure root analytics logger
    analytics_logger = logging.getLogger("apps.analytics")
    analytics_logger.setLevel(logging.INFO)

    # Remove existing handlers
    analytics_logger.handlers = []

    # Add JSON handler
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(StructuredJSONFormatter())
    analytics_logger.addHandler(handler)

    # Prevent propagation to root logger
    analytics_logger.propagate = False


def get_correlation_id(request) -> str:
    """
    Extract or generate a correlation ID from a request.

    Checks for X-Correlation-ID header, falls back to request ID.
    """
    correlation_id = getattr(request, "headers", {}).get("X-Correlation-ID", None)
    if not correlation_id:
        correlation_id = getattr(request, "request_id", None)
    if not correlation_id:
        import uuid

        correlation_id = str(uuid.uuid4())
    return correlation_id
