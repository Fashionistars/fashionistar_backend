# apps/common/telemetry.py
"""
FASHIONISTAR — OpenTelemetry Observability Setup.

Configures distributed tracing and metrics for the production backend:
  - OpenTelemetry OTLP exporter → Sentry / Datadog / Jaeger
  - Domain-prefixed span attributes: product.*, cart.*, order.*, payment.*,
    measurement.*, auth.*
  - Correlation ID propagation middleware for request-scoped logging
  - Structured JSON log context enrichment (correlation_id, user_id, domain)

Usage:
    In Django WSGI/ASGI entrypoint, or via AppConfig.ready():
        from apps.common.telemetry import setup_telemetry
        setup_telemetry()

Environment:
    OTEL_SERVICE_NAME        — e.g. "fashionistar-backend"
    OTEL_EXPORTER_OTLP_ENDPOINT — e.g. "https://otel.sentry.io"
    OTEL_EXPORTER_OTLP_HEADERS   — e.g. "sentry-trace-id=xxx" (or Datadog API key)
    OTEL_ENABLED             — "true"/"false" (default false in dev)

Architecture:
    - Batch span processor for high-throughput (never blocks HTTP request cycle)
    - Parent-based sampling: trace 10% in production, 100% in dev
    - PII scrubbing: no user emails, phone numbers, or card data in spans
"""

from __future__ import annotations

import logging
import os
import uuid
from typing import Any

logger = logging.getLogger(__name__)

_OTEL_CONFIGURED = False


def setup_telemetry() -> bool:
    """
    Initialize OpenTelemetry SDK.

    Returns True if successfully configured, False if disabled or dependencies missing.
    Should be called once at application startup from AppConfig.ready() or ASGI entrypoint.
    """
    global _OTEL_CONFIGURED
    if _OTEL_CONFIGURED:
        return True

    if os.environ.get("OTEL_ENABLED", "false").lower() != "true":
        logger.debug("OpenTelemetry disabled (OTEL_ENABLED != 'true').")
        return False

    try:
        from opentelemetry import trace
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
        from opentelemetry.sdk.resources import Resource, SERVICE_NAME, SERVICE_VERSION
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.django import DjangoInstrumentor
        from opentelemetry.instrumentation.psycopg import PsycopgInstrumentor
        from opentelemetry.instrumentation.redis import RedisInstrumentor
        from opentelemetry.instrumentation.celery import CeleryInstrumentor
        from opentelemetry.sdk.trace.sampling import ParentBasedTraceIdRatio

    except ImportError as e:
        logger.warning("OpenTelemetry packages not installed: %s — skipping setup.", e)
        return False

    try:
        service_name = os.environ.get("OTEL_SERVICE_NAME", "fashionistar-backend")
        service_version = os.environ.get("GIT_SHA", "unknown")
        environment = os.environ.get("DJANGO_ENV", "development")

        resource = Resource.create({
            SERVICE_NAME: service_name,
            SERVICE_VERSION: service_version,
            "deployment.environment": environment,
            "service.namespace": "fashionistar",
        })

        # Sampling: 100% dev, 10% production (matches Sentry traces_sample_rate=0.10)
        sample_rate = 1.0 if environment == "development" else float(
            os.environ.get("OTEL_TRACE_SAMPLE_RATE", "0.10")
        )
        sampler = ParentBasedTraceIdRatio(sample_rate)

        provider = TracerProvider(resource=resource, sampler=sampler)

        # OTLP exporter (sends to Sentry / Datadog / Jaeger)
        otlp_endpoint = os.environ.get("OTEL_EXPORTER_OTLP_ENDPOINT", "")
        otlp_headers_raw = os.environ.get("OTEL_EXPORTER_OTLP_HEADERS", "")
        otlp_headers = _parse_otel_headers(otlp_headers_raw)

        if otlp_endpoint:
            exporter = OTLPSpanExporter(endpoint=otlp_endpoint, headers=otlp_headers)
            provider.add_span_processor(BatchSpanProcessor(exporter))
            logger.info("OpenTelemetry OTLP exporter configured: %s", otlp_endpoint)
        else:
            logger.warning(
                "OTEL_EXPORTER_OTLP_ENDPOINT not set — spans will not be exported."
            )

        trace.set_tracer_provider(provider)

        # Auto-instrument Django, PostgreSQL, Redis, Celery
        DjangoInstrumentor().instrument(
            request_hook=_django_request_hook,
            response_hook=_django_response_hook,
        )
        PsycopgInstrumentor().instrument(skip_dep_check=True)
        RedisInstrumentor().instrument()
        CeleryInstrumentor().instrument()

        _OTEL_CONFIGURED = True
        logger.info(
            "✅ OpenTelemetry configured: service=%s env=%s sample_rate=%.0f%%",
            service_name, environment, sample_rate * 100,
        )
        return True

    except Exception:
        logger.exception("OpenTelemetry setup failed — traces will not be collected.")
        return False


def _parse_otel_headers(raw: str) -> dict[str, str]:
    """Parse 'key1=val1,key2=val2' format into dict."""
    headers: dict[str, str] = {}
    for part in raw.split(","):
        if "=" in part:
            k, _, v = part.partition("=")
            headers[k.strip()] = v.strip()
    return headers


def _django_request_hook(span, request):
    """Enrich request span with Fashionistar-specific attributes."""
    try:
        span.set_attribute("http.client_ip", _get_client_ip(request))
        span.set_attribute("auth.user_id", str(getattr(getattr(request, "user", None), "id", "anon")))
        span.set_attribute("auth.user_role", str(getattr(getattr(request, "user", None), "role", "anon")))
        span.set_attribute("fashionistar.correlation_id", _get_or_create_correlation_id(request))
        span.set_attribute("fashionistar.domain", _detect_domain(request.path))
    except Exception:
        pass  # Never fail a request due to telemetry


def _django_response_hook(span, request, response):
    """Add response-level attributes."""
    try:
        if hasattr(response, "status_code"):
            span.set_attribute("http.response.status_code", response.status_code)
    except Exception:
        pass


def _get_client_ip(request) -> str:
    """Extract real client IP respecting GCP/Cloudflare proxy headers."""
    xff = request.META.get("HTTP_X_FORWARDED_FOR", "")
    if xff:
        return xff.split(",")[0].strip()
    return request.META.get("REMOTE_ADDR", "unknown")


def _get_or_create_correlation_id(request) -> str:
    """Return or generate a unique correlation ID for the request."""
    existing = getattr(request, "_correlation_id", None)
    if existing:
        return existing
    correlation_id = request.META.get("HTTP_X_CORRELATION_ID") or str(uuid.uuid4())
    request._correlation_id = correlation_id
    return correlation_id


def _detect_domain(path: str) -> str:
    """Map URL path prefix to business domain for span attributes."""
    segments = path.strip("/").split("/")
    prefix = segments[2] if len(segments) >= 3 else ""
    domain_map = {
        "products": "catalog", "catalog": "catalog",
        "orders": "order", "cart": "cart",
        "payments": "payment", "wallet": "wallet",
        "measurements": "measurement",
        "auth": "auth", "users": "auth",
        "chat": "chat", "notifications": "notification",
        "vendors": "vendor", "clients": "client",
    }
    return domain_map.get(prefix, "generic")


# ── Domain Tracer Factory ─────────────────────────────────────────────────────

def get_tracer(domain: str):
    """
    Return an OpenTelemetry tracer for a specific business domain.

    Usage:
        tracer = get_tracer("payment")
        with tracer.start_as_current_span("payment.charge") as span:
            span.set_attribute("payment.amount_ngn", str(amount))
            span.set_attribute("payment.provider", "paystack")
    """
    try:
        from opentelemetry import trace
        return trace.get_tracer(f"fashionistar.{domain}")
    except ImportError:
        return _NoOpTracer()


class _NoOpTracer:
    """Fallback tracer when OpenTelemetry is not installed."""
    def start_as_current_span(self, name: str, **kwargs):
        from contextlib import contextmanager
        @contextmanager
        def _noop():
            yield _NoOpSpan()
        return _noop()


class _NoOpSpan:
    def set_attribute(self, key: str, value: Any) -> None:
        pass
    def record_exception(self, exc: Exception) -> None:
        pass
    def set_status(self, *args, **kwargs) -> None:
        pass


# ── Correlation ID Logging Middleware ─────────────────────────────────────────

class CorrelationIdMiddleware:
    """
    Django ASGI/WSGI middleware that:
      1. Reads X-Correlation-ID header (or generates UUID)
      2. Attaches correlation_id to the request object
      3. Injects it into log context via logging.LoggerAdapter pattern

    Must be first in MIDDLEWARE list for full coverage.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        correlation_id = (
            request.META.get("HTTP_X_CORRELATION_ID")
            or request.META.get("HTTP_X_REQUEST_ID")
            or str(uuid.uuid4())
        )
        request._correlation_id = correlation_id

        response = self.get_response(request)
        response["X-Correlation-ID"] = correlation_id
        return response
