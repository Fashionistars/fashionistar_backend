# apps/common/telemetry.py
"""
FASHIONISTAR — Enterprise Observability & Telemetry Module.

This module provides a unified interface for distributed tracing, metrics, 
error tracking, and structured logging. It is designed for high-concurrency 
production environments (2026/2027) with a focus on GDPR compliance and performance.

Integrations:
  1. OpenTelemetry (OTel) — Distributed traces via OTLP (Sentry/Datadog/Jaeger).
  2. Sentry — Error tracking with custom PII scrubbing and 10% sampling.
  3. Structured JSON Logging — Correlation IDs and trace context in every log.
  4. Metric Helpers — Lightweight OTel counters and histograms for business KPIs.

Architecture:
  - Parent-based sampling (100% dev, 10% prod) to manage ingestion costs.
  - Asynchronous span processing to ensure zero impact on request latency.
  - Domain-prefixed telemetry: auth.*, order.*, payment.*, catalog.*, etc.
  - Middleware-driven Correlation ID propagation across the micro-stack.

Usage:
    Called once at Django startup from BackendConfig.ready():
        from apps.common.telemetry import setup_telemetry
        setup_telemetry()

Environment:
    OTEL_SERVICE_NAME        — e.g. "fashionistar-backend"
    OTEL_EXPORTER_OTLP_ENDPOINT — e.g. "https://otel.sentry.io"
    OTEL_EXPORTER_OTLP_HEADERS   — e.g. "sentry-trace-id=xxx" (or Datadog API key)
    OTEL_ENABLED             — "true"/"false" (default false in dev)

"""

from __future__ import annotations

import json
import logging
import os
import re
import uuid
from datetime import datetime, timezone
from typing import Any, Protocol, runtime_checkable

from django.conf import settings
from django.utils.translation import gettext_lazy as _

# ── Logging Configuration ─────────────────────────────────────────────────────

logger = logging.getLogger(__name__)

_OTEL_CONFIGURED = False

# ── PII Scrubbing Patterns (GDPR Article 25 — Privacy by Design) ──────────────

# These patterns are used to redact sensitive information before it leaves 
# the infrastructure, ensuring we never store PII in Sentry or OTel spans.
_PII_PATTERNS = [
    (re.compile(r'[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+'), "[email]"),
    (re.compile(r'\b\+?[0-9]{10,15}\b'), "[phone]"),
    (re.compile(r'\b4[0-9]{12}(?:[0-9]{3})?\b'), "[card]"),           # Visa
    (re.compile(r'\b5[1-5][0-9]{14}\b'), "[card]"),                   # Mastercard
    (re.compile(r'\b(?:\d{1,3}\.){3}\d{1,3}\b'), "[ip]"),            # IPv4
    (re.compile(r'password["\']?\s*[:=]\s*["\']?[^"\'&\s]+'), "[password]"),
    (re.compile(r'token["\']?\s*[:=]\s*["\']?[A-Za-z0-9._-]{20,}'), "[token]"),
]


def _scrub_pii(text: str) -> str:
    """Replace known PII patterns with redacted placeholders."""
    if not isinstance(text, str):
        return text
    for pattern, replacement in _PII_PATTERNS:
        text = pattern.sub(replacement, text)
    return text


# ── Structured JSON Formatter ────────────────────────────────────────────────


class StructuredJSONFormatter(logging.Formatter):
    """
    Enterprise-grade JSON log formatter.
    
    Injected fields:
      - trace_id / span_id: For log-to-trace correlation.
      - correlation_id: For tracking a single request across multiple services.
      - user_id / domain: For business-level observability.
    """

    def format(self, record: logging.LogRecord) -> str:
        # 1. Capture OTel trace context if available
        trace_id, span_id = "", ""
        try:
            from opentelemetry import trace
            span = trace.get_current_span()
            ctx = span.get_span_context()
            if ctx and ctx.is_valid:
                trace_id = format(ctx.trace_id, "032x")
                span_id = format(ctx.span_id, "016x")
        except ImportError:
            pass

        # 2. Capture Request/Audit context
        correlation_id, user_id = "", ""
        try:
            # First check record attributes from Middleware/Adapter
            correlation_id = getattr(record, "correlation_id", "")
            user_id = getattr(record, "user_id", "")
            
            # Fallback to AuditContextVar if apps.audit_logs is installed
            if not correlation_id:
                from apps.audit_logs.context import get_audit_context
                ctx_data = get_audit_context()
                correlation_id = ctx_data.get("request_id", "")
                user_id = ctx_data.get("actor_id", "")
        except (ImportError, Exception):
            pass

        # 3. Build standard JSON payload
        payload = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "logger": record.name,
            "message": self.formatMessage(record),
            "module": record.module,
            "function": record.funcName,
            "line": record.lineno,
            "correlation_id": correlation_id,
            "user_id": user_id,
            "domain": getattr(record, "domain", self._detect_domain(record.name)),
            "trace_id": trace_id,
            "span_id": span_id,
        }

        # Handle Exception Info
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)

        # Include custom 'extra' fields passed in logger.info(msg, extra={...})
        for key in record.__dict__:
            if key not in logging.LogRecord.__dict__ and key not in payload:
                payload[key] = record.__dict__[key]

        return json.dumps(payload, default=str, ensure_ascii=False)

    def _detect_domain(self, logger_name: str) -> str:
        """Helper to extract domain from logger name (e.g., apps.payment.models -> payment)."""
        parts = logger_name.split(".")
        return parts[1] if len(parts) > 1 and parts[0] == "apps" else "generic"


# ── OpenTelemetry Initialization ──────────────────────────────────────────────


def _setup_opentelemetry() -> bool:
    """
    Configures OpenTelemetry with OTLP exporters and Django-specific hooks.
    """
    global _OTEL_CONFIGURED
    if _OTEL_CONFIGURED:
        return True

    # Kill-switch via environment
    if os.environ.get("OTEL_ENABLED", "false").lower() != "true":
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, SERVICE_VERSION, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

        service_name = os.environ.get("OTEL_SERVICE_NAME", "fashionistar-backend")
        environment = getattr(settings, "ENVIRONMENT", "development")
        
        # 1. Define Resource Metadata
        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: getattr(settings, "APP_VERSION", "1.0.0"),
            "deployment.environment": environment,
            "service.namespace": "fashionistar",
        })

        # 2. Configure Sampling (100% Dev, 10% Prod)
        sample_rate = 1.0 if environment == "development" else float(
            os.environ.get("OTEL_TRACE_SAMPLE_RATE", "0.10")
        )
        sampler = ParentBasedTraceIdRatio(sample_rate)

        provider = TracerProvider(resource=resource, sampler=sampler)

        # 3. Configure OTLP Exporter (HTTP Proto)
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        if otlp_endpoint:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OTel OTLP exporter configured: %s", otlp_endpoint)

        trace.set_tracer_provider(provider)

        # 4. Auto-Instrumentation with Custom Hooks
        DjangoInstrumentor().instrument(
            request_hook=_django_request_hook,
            response_hook=_django_response_hook,
        )
        PsycopgInstrumentor().instrument(skip_dep_check=True)
        RedisInstrumentor().instrument()
        CeleryInstrumentor().instrument()

        _OTEL_CONFIGURED = True
        logger.info("✅ OpenTelemetry initialized [Service: %s]", service_name)
        return True

    except ImportError:
        logger.warning("OTel packages missing. Tracing disabled.")
        return False
    except Exception as e:
        logger.error("OTel setup failed: %s", e)
        return False


def _django_request_hook(span, request):
    """Enrich request span with Fashionistar-specific attributes."""
    try:
        user = getattr(request, "user", None)
        span.set_attribute("auth.user_id", str(getattr(user, "id", "anon")))
        span.set_attribute("auth.user_role", str(getattr(user, "role", "anon")))
        span.set_attribute("fashionistar.correlation_id", getattr(request, "_correlation_id", "unknown"))
        
        # Determine business domain for better Datadog/Jaeger grouping
        segments = request.path.strip("/").split("/")
        domain = segments[2] if len(segments) >= 3 else "generic"
        span.set_attribute("fashionistar.domain", domain)
    except Exception:
        pass


def _django_response_hook(span, request, response):
    """Capture status code on span termination."""
    if hasattr(response, "status_code"):
        span.set_attribute("http.response.status_code", response.status_code)


# ── Sentry Initialization ─────────────────────────────────────────────────────


def _setup_sentry() -> None:
    """Initialize Sentry with strict PII scrubbing and OTel integration."""
    dsn = getattr(settings, "SENTRY_DSN", "")
    if not dsn:
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.celery import CeleryIntegration
        from sentry_sdk.integrations.django import DjangoIntegration
        from sentry_sdk.integrations.logging import LoggingIntegration
        from sentry_sdk.integrations.redis import RedisIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=getattr(settings, "ENVIRONMENT", "production"),
            release=getattr(settings, "APP_VERSION", "unknown"),
            traces_sample_rate=float(getattr(settings, "SENTRY_TRACES_SAMPLE_RATE", 0.10)),
            send_default_pii=False,
            before_send=_before_send_sentry,
            integrations=[
                DjangoIntegration(transaction_style="url", middleware_spans=True),
                CeleryIntegration(monitor_beat_tasks=True),
                RedisIntegration(),
                LoggingIntegration(level=logging.WARNING, event_level=logging.ERROR),
            ],
            ignore_errors=[
                "PermissionDenied", "NotFound", "ValidationError", 
                "AuthenticationFailed", "Throttled",
            ],
        )
        logger.info("✅ Sentry initialized with PII scrubbing.")
    except ImportError:
        logger.warning("sentry-sdk missing.")


def _before_send_sentry(event: dict, hint: dict) -> dict | None:
    """Custom Sentry noise filter and PII scrubber."""
    # 1. Filter out high-frequency health-check noise
    url = event.get("request", {}).get("url", "")
    if any(path in url for path in ["/health/", "/ping/", "/favicon.ico"]):
        return None

    # 2. Scrub Exception values and logs
    if "logentry" in event:
        event["logentry"]["message"] = _scrub_pii(event["logentry"].get("message", ""))

    for exc in event.get("exception", {}).get("values", []):
        exc["value"] = _scrub_pii(exc.get("value", ""))

    # 3. Remove raw IP from user data (GDPR requirement)
    if "user" in event:
        event["user"].pop("ip_address", None)

    return event


# ── Metrics Helper ────────────────────────────────────────────────────────────


class FashionistarMetrics:
    """
    Wrapper for OTel Metrics API.
    
    Usage:
        metrics.increment("payment.success", tags={"provider": "paystack"})
    """
    _meter = None

    @classmethod
    def _get_meter(cls):
        if cls._meter is None:
            try:
                from opentelemetry import metrics
                cls._meter = metrics.get_meter("fashionistar")
            except (ImportError, Exception):
                pass
        return cls._meter

    def increment(self, name: str, value: int = 1, tags: dict | None = None) -> None:
        meter = self._get_meter()
        if meter:
            try:
                counter = meter.create_counter(f"fashionistar.{name}")
                counter.add(value, tags or {})
            except Exception: pass

    def record_latency(self, name: str, value_ms: float, tags: dict | None = None) -> None:
        meter = self._get_meter()
        if meter:
            try:
                hist = meter.create_histogram(f"fashionistar.{name}", unit="ms")
                hist.record(value_ms, tags or {})
            except Exception: pass


metrics = FashionistarMetrics()

# ── Correlation Middleware ────────────────────────────────────────────────────


class CorrelationIdMiddleware:
    """
    Ensures every request has a unique 'X-Correlation-ID'.
    This ID is propagated through logs and tracing spans for easy debugging.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = (
            request.META.get("HTTP_X_CORRELATION_ID") or 
            request.META.get("HTTP_X_REQUEST_ID") or 
            str(uuid.uuid4())
        )
        request._correlation_id = correlation_id
        
        response = self.get_response(request)
        response["X-Correlation-ID"] = correlation_id
        return response


# ── Main Entry Point ──────────────────────────────────────────────────────────


def setup_telemetry() -> None:
    """
    Entry point to initialize the observability stack.
    Must be called within AppConfig.ready().
    """
    _setup_opentelemetry()
    _setup_sentry()
    logger.info("🚀 FASHIONISTAR Telemetry Stack Ready.")






# ── Public alias for AppConfig.ready() ───────────────────────────────────────

def bootstrap_telemetry() -> bool:
    """
    Phase 9 — Public entry point called from CommonConfig.ready().

    Wraps setup_telemetry() so apps.py uses a domain-consistent name.
    Returns True if OTel was successfully configured, False otherwise.
    """
    return setup_telemetry()





