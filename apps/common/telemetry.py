# apps/common/telemetry.py
"""
FASHIONISTAR — Enterprise Observability & Telemetry Module.

Integrates:
  1. OpenTelemetry (OTel) — distributed traces + metrics
  2. Sentry — error tracking with PII scrubbing + 10% trace sampling
  3. Structured JSON logging — correlation_id, user_id, domain on every log record

Usage:
  Called once at Django startup from BackendConfig.ready() in backend/apps.py.
  All subsequent logging via standard `logging.getLogger(__name__)` will
  automatically include structured fields via StructuredJSONFormatter.

OpenTelemetry export targets:
  - OTEL_EXPORTER_OTLP_ENDPOINT (env) → Datadog Agent / Jaeger / Cloud Trace
  - Sentry OTel integration → Sentry Performance

Sentry PII scrubbing:
  - before_send() strips email, phone, ip_address, credit card patterns
  - Event fingerprinting by domain prefix (auth.*, order.*, payment.*)
  - Trace sample rate: 10% (SENTRY_TRACES_SAMPLE_RATE env, default 0.10)

Metric prefixes (matching Datadog metric naming convention):
  fashionistar.auth.*         → login, token_refresh, 2fa_verify
  fashionistar.order.*        → placed, paid, shipped, delivered, disputed
  fashionistar.payment.*      → initiated, succeeded, failed, refunded
  fashionistar.cart.*         → add, remove, checkout_initiated, abandoned
  fashionistar.measurement.*  → scan_started, scan_completed, share_created
  fashionistar.wallet.*       → credit, debit, escrow_hold, payout_requested

Architecture:
  - OTel SDK: opentelemetry-sdk + opentelemetry-instrumentation-django
  - Metrics: opentelemetry-api Counter/Histogram via PrometheusMetricReader (optional)
  - Sentry: sentry-sdk[django] with OTel transport
"""

from __future__ import annotations

import logging
import re
import json
from datetime import datetime, timezone
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# PII Scrubbing Patterns (GDPR Article 25 — Privacy by Design)
# ─────────────────────────────────────────────────────────────────────────────

_PII_PATTERNS = [
    (re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'), "[email]"),
    (re.compile(r'\b\+?[0-9]{10,15}\b'), "[phone]"),
    (re.compile(r'\b4[0-9]{12}(?:[0-9]{3})?\b'), "[card]"),        # Visa
    (re.compile(r'\b5[1-5][0-9]{14}\b'), "[card]"),                  # Mastercard
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), "[ip]"),           # IPv4
    (re.compile(r'password["\']?\s*[:=]\s*["\']?[^"\'&\s]+'), "[password]"),
    (re.compile(r'token["\']?\s*[:=]\s*["\']?[A-Za-z0-9._-]{20,}'), "[token]"),
]


def _scrub_pii(text: str) -> str:
    """Replace known PII patterns with redacted placeholders."""
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


def _before_send_sentry(event: dict, hint: dict) -> dict | None:
    """
    Sentry before_send hook.

    - Scrubs PII from event message, exception values, and request body.
    - Drops health-check errors (noisy, non-actionable).
    - Adds fingerprint based on Django logger name for deduplication.
    """
    # Drop health-check noise
    request = event.get("request", {})
    url = request.get("url", "")
    if "/health/" in url or "/ping/" in url:
        return None

    # Scrub message
    if "logentry" in event:
        msg = event["logentry"].get("message", "")
        event["logentry"]["message"] = _scrub_pii(msg)

    # Scrub exception values
    exceptions = event.get("exception", {}).get("values", [])
    for exc in exceptions:
        val = exc.get("value", "")
        exc["value"] = _scrub_pii(val)

    # Scrub request body
    if "data" in request:
        body = json.dumps(request["data"]) if isinstance(request["data"], dict) else str(request["data"])
        request["data"] = _scrub_pii(body)

    # Strip IP from user context (GDPR)
    if "user" in event:
        event["user"].pop("ip_address", None)

    # Add domain fingerprint from logger name for deduplication
    extra = event.get("extra", {})
    domain = extra.get("domain", "unknown")
    if domain != "unknown":
        event.setdefault("fingerprint", ["{{ default }}", domain])

    return event


# ─────────────────────────────────────────────────────────────────────────────
# Structured JSON Formatter
# ─────────────────────────────────────────────────────────────────────────────


class StructuredJSONFormatter(logging.Formatter):
    """
    Emits every log record as a single-line JSON object.

    Standard fields on every record:
      timestamp, level, logger, message, module, function, line
      correlation_id, user_id, domain  ← injected from ContextVar if set
    """

    def format(self, record: logging.LogRecord) -> str:
        # Try to get OpenTelemetry trace context
        trace_id = ""
        span_id = ""
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.is_valid:
                trace_id = format(ctx.trace_id, "032x")
                span_id = format(ctx.span_id, "016x")
        except Exception:
            pass

        # Try to get audit context (correlation_id, user_id)
        correlation_id = ""
        user_id = ""
        try:
            from apps.audit_logs.context import get_audit_context
            ctx_data = get_audit_context()
            correlation_id = ctx_data.get("request_id", "")
            user_id = ctx_data.get("actor_id", "")
        except Exception:
            pass

        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self.formatMessage(record),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "correlation_id": correlation_id or getattr(record, "correlation_id", ""),
            "user_id": user_id or getattr(record, "user_id", ""),
            "domain": getattr(record, "domain", record.name.split(".")[1] if record.name.startswith("apps.") else ""),
            "trace_id": trace_id,
            "span_id": span_id,
        }

        # Include exception info if present
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Include any extra fields added by the caller
        for key in record.__dict__:
            if key not in logging.LogRecord.__dict__ and key not in payload:
                payload[key] = record.__dict__[key]

        return json.dumps(payload, default=str, ensure_ascii=False)


# ─────────────────────────────────────────────────────────────────────────────
# OpenTelemetry Initialization
# ─────────────────────────────────────────────────────────────────────────────


def _setup_opentelemetry() -> None:
    """
    Initialize OpenTelemetry SDK with OTLP exporter.

    Safe to call even if opentelemetry packages are not installed
    (graceful degradation — just logs a warning).
    """
    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.celery import CeleryInstrumentor

        otlp_endpoint = getattr(settings, "OTEL_EXPORTER_OTLP_ENDPOINT", "")
        service_name = getattr(settings, "OTEL_SERVICE_NAME", "fashionistar-backend")

        # Set up tracer provider
        provider = TracerProvider()

        # Add OTLP exporter if endpoint is configured
        if otlp_endpoint:
            try:
                from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
                exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
                provider.add_span_processor(BatchSpanProcessor(exporter))
                logger.info("OTel OTLP exporter configured: %s", otlp_endpoint)
            except Exception as exc:
                logger.warning("OTel OTLP exporter failed to configure: %s", exc)

        trace.set_tracer_provider(provider)

        # Auto-instrument Django, PostgreSQL, Redis, Celery
        DjangoInstrumentor().instrument()
        try:
            PsycopgInstrumentor().instrument()
        except Exception:
            pass
        try:
            RedisInstrumentor().instrument()
        except Exception:
            pass
        try:
            CeleryInstrumentor().instrument()
        except Exception:
            pass

        logger.info("OpenTelemetry initialized: service=%s", service_name)

    except ImportError:
        logger.warning(
            "opentelemetry-sdk not installed. OTel tracing disabled. "
            "Install: pip install opentelemetry-sdk opentelemetry-instrumentation-django"
        )
    except Exception as exc:
        logger.warning("OpenTelemetry initialization failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Sentry Initialization
# ─────────────────────────────────────────────────────────────────────────────


def _setup_sentry() -> None:
    """
    Initialize Sentry with PII scrubbing, performance tracing, and OTel integration.
    """
    dsn = getattr(settings, "SENTRY_DSN", "")
    if not dsn:
        logger.info("SENTRY_DSN not set — Sentry disabled.")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.redis import RedisIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration

        environment = getattr(settings, "ENVIRONMENT", "production")
        traces_sample_rate = float(getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.10))
        release = getattr(settings, "APP_VERSION", "unknown")

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            release=release,
            traces_sample_rate=traces_sample_rate,
            send_default_pii=False,           # NEVER send PII by default
            before_send=_before_send_sentry,  # Custom PII scrubbing + noise filter
            integrations=[
                DjangoIntegration(
                    transaction_style="url",
                    middleware_spans=True,
                    signals_spans=False,      # Too noisy for high-volume Django
                    cache_spans=True,
                ),
                CeleryIntegration(monitor_beat_tasks=True),
                RedisIntegration(),
                LoggingIntegration(
                    level=logging.WARNING,        # Capture WARNING+ as breadcrumbs
                    event_level=logging.ERROR,    # Send ERROR+ as Sentry events
                ),
            ],
            # Ignore common non-actionable exceptions
            ignore_errors=[
                "PermissionDenied",
                "NotFound",
                "ValidationError",
                "AuthenticationFailed",
                "NotAuthenticated",
                "Throttled",
            ],
        )
        logger.info(
            "Sentry initialized: env=%s traces=%.0f%%",
            environment, traces_sample_rate * 100,
        )

    except ImportError:
        logger.warning(
            "sentry-sdk not installed. Install: pip install sentry-sdk[django]"
        )
    except Exception as exc:
        logger.warning("Sentry initialization failed: %s", exc)


# ─────────────────────────────────────────────────────────────────────────────
# Metric Helpers (OTel Counter/Histogram)
# ─────────────────────────────────────────────────────────────────────────────


class FashionistarMetrics:
    """
    Lightweight metric helpers wrapping OTel Counter/Histogram.

    Usage:
        from apps.common.telemetry import metrics
        metrics.increment("order.placed", tags={"payment_method": "card"})
        metrics.record_latency("payment.duration_ms", 42.5)
    """

    _meter = None

    @classmethod
    def _get_meter(cls):
        if cls._meter is None:
            try:
                from opentelemetry import metrics
                cls._meter = metrics.get_meter("fashionistar")
            except ImportError:
                pass
        return cls._meter

    def increment(self, name: str, value: int = 1, tags: dict | None = None) -> None:
        """Increment a counter metric."""
        meter = self._get_meter()
        if meter is None:
            return
        try:
            counter = meter.create_counter(f"fashionistar.{name}")
            counter.add(value, tags or {})
        except Exception:
            pass

    def record_latency(self, name: str, value_ms: float, tags: dict | None = None) -> None:
        """Record a histogram value (latency in milliseconds)."""
        meter = self._get_meter()
        if meter is None:
            return
        try:
            histogram = meter.create_histogram(f"fashionistar.{name}", unit="ms")
            histogram.record(value_ms, tags or {})
        except Exception:
            pass


metrics = FashionistarMetrics()


# ─────────────────────────────────────────────────────────────────────────────
# Main Entry Point — Called from BackendConfig.ready()
# ─────────────────────────────────────────────────────────────────────────────


def setup_telemetry() -> None:
    """
    Initialize all observability integrations.

    Called ONCE from `backend.apps.BackendConfig.ready()`.
    Idempotent — safe to call in test environments (Sentry/OTel silently skip
    if DSN/endpoint not configured).
    """
    _setup_opentelemetry()
    _setup_sentry()
    logger.info("FASHIONISTAR telemetry stack initialized.")
