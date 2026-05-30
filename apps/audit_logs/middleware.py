# apps/audit_logs/middleware.py
"""
Enterprise Audit Context Middleware — Production Grade (ASGI-Safe v2.0).

ASGI SAFETY FIX (Phase 1):
  threading.local() is thread-scoped. Under Uvicorn/ASGI, multiple coroutines
  share one OS thread. Every request was seeing every other request's audit
  context — a GDPR violation and the primary cause of corrupted audit trails.

  Fix: contextvars.ContextVar (Python 3.7+) is task-scoped, not thread-scoped.
  Each asyncio Task gets its own isolated copy — exactly what ASGI requires.

Dual-mode pattern (same as apps.common.middleware):
  __call__  = sync entry point  (WSGI: gunicorn, manage.py runserver)
  __acall__ = async entry point (ASGI: Uvicorn, Daphne)
  Django ≥ 3.1 checks __acall__ first; ASGI handler awaits it directly.

Enhancements vs. v1:
  [E1] ContextVar: ASGI-safe task-local context (replaces threading.local).
  [E2] Dual __call__ / __acall__: zero sync_to_async handoff cost.
  [E3] Auto Failed API Capture: fire-and-forget on 4xx/5xx via
       asyncio.create_task() (ASGI) or daemon threading.Thread (WSGI).
       The response path is NEVER blocked by audit I/O.

Usage in settings:
    MIDDLEWARE = [
        ...
        'apps.audit_logs.middleware.AuditContextMiddleware',
        ...
    ]
"""

from __future__ import annotations

import asyncio
import logging
import threading
import uuid
from contextlib import contextmanager
from contextvars import ContextVar
from functools import wraps
from typing import Any

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

logger = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# ASGI-safe context store
# ─────────────────────────────────────────────────────────────────────────────
# ContextVar is task-scoped under asyncio (each coroutine/Task gets its own
# copy) AND thread-scoped under WSGI (each thread gets its own copy via
# Python's contextvars integration with threading). This replaces the old
# threading.local() that leaked context between concurrent ASGI requests.

_audit_ctx: ContextVar[dict] = ContextVar("audit_ctx", default={})


def get_audit_context() -> dict:
    """
    Return the current request's audit context dict.

    Returns an empty dict outside of a request (e.g., Celery tasks)
    unless audit_context_override() is active.

    Returns:
        dict: Current audit context (ip_address, user_agent, actor, etc.).
    """
    return _audit_ctx.get()


def extract_client_context(request: Any = None) -> dict:
    """
    Extract all request-specific and frontend-enriched audit fields.

    Can be passed directly as kwargs or metadata to Celery tasks to
    propagate the client context into background workers.

    Args:
        request: Optional Django HttpRequest. If None, returns stored context.

    Returns:
        dict: Audit context fields for downstream consumption.
    """
    ctx = get_audit_context()
    if request:
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")
        return {
            "client_device_id":  request.META.get("HTTP_X_DEVICE_ID") or ctx.get("client_device_id"),
            "client_timezone":   request.META.get("HTTP_X_CLIENT_TIMEZONE") or ctx.get("client_timezone"),
            "client_locale":     request.META.get("HTTP_X_CLIENT_LOCALE") or ctx.get("client_locale"),
            "client_platform":   request.META.get("HTTP_X_CLIENT_PLATFORM") or ctx.get("client_platform"),
            "client_geo_lat":    request.META.get("HTTP_X_CLIENT_GEO_LAT") or ctx.get("client_geo_lat"),
            "client_geo_lng":    request.META.get("HTTP_X_CLIENT_GEO_LNG") or ctx.get("client_geo_lng"),
            "client_geo_acc":    request.META.get("HTTP_X_CLIENT_GEO_ACCURACY") or ctx.get("client_geo_acc"),
            "ip_address":        ip or ctx.get("ip_address"),
            "user_agent":        request.META.get("HTTP_USER_AGENT", "") or ctx.get("user_agent"),
            "correlation_id":    getattr(request, "correlation_id", None) or ctx.get("correlation_id"),
        }
    return {
        "client_device_id": ctx.get("client_device_id"),
        "client_timezone":  ctx.get("client_timezone"),
        "client_locale":    ctx.get("client_locale"),
        "client_platform":  ctx.get("client_platform"),
        "client_geo_lat":   ctx.get("client_geo_lat"),
        "client_geo_lng":   ctx.get("client_geo_lng"),
        "client_geo_acc":   ctx.get("client_geo_acc"),
        "ip_address":       ctx.get("ip_address"),
        "user_agent":       ctx.get("user_agent"),
        "correlation_id":   ctx.get("correlation_id"),
    }


@contextmanager
def audit_context_override(context_dict: dict):
    """
    Context manager to temporarily override the ContextVar audit context.

    ASGI-safe: ContextVar.set() returns a Token; ContextVar.reset(token)
    restores the previous value — no shared mutable state between tasks.

    Useful inside Celery tasks to propagate client context metadata:

        with audit_context_override(task_kwargs["audit_client_context"]):
            ...do work...

    Args:
        context_dict: Dict of audit fields to inject into the context.
    """
    if context_dict and "client_geo_accuracy_m" in context_dict:
        context_dict = dict(context_dict)
        context_dict["client_geo_acc"] = context_dict.pop("client_geo_accuracy_m")
    token = _audit_ctx.set(context_dict or {})
    try:
        yield
    finally:
        _audit_ctx.reset(token)


def propagate_audit_context(func):
    """
    Decorator to wrap a Celery task function.

    If ``audit_client_context`` is present in kwargs, extracts it and runs
    the task inside ``audit_context_override`` so the ContextVar is populated
    for the task's execution context.

    Args:
        func: The Celery task function to decorate.

    Returns:
        Wrapped function with audit context injection.
    """
    @wraps(func)
    def wrapper(*args, **kwargs):
        audit_client_context = kwargs.pop("audit_client_context", None)
        if audit_client_context:
            with audit_context_override(audit_client_context):
                return func(*args, **kwargs)
        return func(*args, **kwargs)
    return wrapper


# ─────────────────────────────────────────────────────────────────────────────
# Auto-capture exemptions (paths / methods too noisy for automatic 4xx/5xx)
# ─────────────────────────────────────────────────────────────────────────────
_AUTO_CAPTURE_EXEMPT_PREFIXES = (
    "/health",
    "/metrics",
    "/static/",
    "/favicon.ico",
    "/__debug__/",
    "/admin/jsi18n/",
)
_AUTO_CAPTURE_EXEMPT_METHODS = frozenset({"OPTIONS", "HEAD"})


# ─────────────────────────────────────────────────────────────────────────────
# Phase 9: Pure context-extraction helpers — zero I/O, safe to call anywhere
# ─────────────────────────────────────────────────────────────────────────────

import re as _re

_API_VERSION_RE = _re.compile(r"/v(\d+)/")


def _extract_api_version(path: str | None) -> str | None:
    """Extract the API version segment from a URL path.

    Scans the path for patterns like /v1/, /v2/, /v3/ and returns
    the version string (e.g. 'v1', 'v2').  Returns None if not found.

    Args:
        path: URL path string (e.g. '/api/v2/orders/').

    Returns:
        str | None: Version string like 'v1', or None if not an API path.
    """
    if not path:
        return None
    m = _API_VERSION_RE.search(path)
    return f"v{m.group(1)}" if m else None


def _safe_content_length(request) -> int | None:
    """Safely extract Content-Length from an HttpRequest.

    Never raises — returns None on any error or when the header is absent.
    Used to populate request_size_bytes for Phase 9 anomaly detection.

    Args:
        request: Django HttpRequest.

    Returns:
        int | None: Content-Length in bytes, or None.
    """
    try:
        cl = request.META.get("CONTENT_LENGTH") or request.META.get("HTTP_CONTENT_LENGTH")
        return int(cl) if cl else None
    except (TypeError, ValueError):
        return None


class AuditContextMiddleware:
    """
    Enterprise audit middleware — ASGI-safe, dual-mode, zero-blocking.

    Responsibilities:
    1. Context injection: populates the ContextVar store with request metadata
       (IP, UA, method, path, actor, correlation_id) so AuditService.log()
       can auto-enrich without requiring callers to pass the request object.

    2. Auto failed API capture: on every response ≥ 400, dispatches an audit
       event ASYNCHRONOUSLY — never blocking the response path:
         * ASGI: asyncio.create_task() → event loop handles it after response.
         * WSGI: daemon threading.Thread() → OS thread handles it off-path.

    Thread Safety (WSGI):
        ContextVar is compatible with threading — each thread gets its own
        isolated copy, behaving identically to the old threading.local().

    Task Safety (ASGI / Uvicorn):
        ContextVar is isolated per asyncio Task — concurrent requests never
        share or pollute each other's audit context.
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        # Tell Django's ASGI handler to call __acall__ instead of __call__
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    # ── WSGI path ─────────────────────────────────────────────────────────────
    def __call__(self, request):
        """Synchronous path — WSGI (gunicorn, manage.py runserver)."""
        ctx, correlation_id = self._build_context(request)
        token = _audit_ctx.set(ctx)
        try:
            response = self.get_response(request)
        except Exception:
            _audit_ctx.reset(token)
            raise

        self._maybe_capture_failed_wsgi(request, response, correlation_id)
        response["X-Correlation-ID"] = correlation_id
        _audit_ctx.reset(token)
        return response

    # ── ASGI path ─────────────────────────────────────────────────────────────
    async def __acall__(self, request):
        """Asynchronous path — ASGI (Uvicorn, Daphne). Zero thread overhead."""
        ctx, correlation_id = self._build_context(request)
        token = _audit_ctx.set(ctx)
        try:
            response = await self.get_response(request)
        except Exception:
            _audit_ctx.reset(token)
            raise

        self._maybe_capture_failed_asgi(request, response, correlation_id)
        response["X-Correlation-ID"] = correlation_id
        _audit_ctx.reset(token)
        return response

    # ── Shared context builder ─────────────────────────────────────────────────
    def _build_context(self, request) -> tuple[dict, str]:
        """
        Build the audit context dict and inject correlation ID into request.

        Pure CPU + header reads — zero I/O. Safe in any execution context.

        Args:
            request: Django HttpRequest.

        Returns:
            tuple[dict, str]: (context_dict, correlation_id)
        """
        correlation_id = (
            request.META.get("HTTP_X_REQUEST_ID")
            or request.META.get("HTTP_X_CORRELATION_ID")
            or str(uuid.uuid4())
        )
        xff = request.META.get("HTTP_X_FORWARDED_FOR")
        ip = xff.split(",")[0].strip() if xff else request.META.get("REMOTE_ADDR")
        user = getattr(request, "user", None)
        actor = user if (user and getattr(user, "is_authenticated", False)) else None
        actor_email = getattr(actor, "email", None)

        ctx = {
            "ip_address":       ip,
            "user_agent":       request.META.get("HTTP_USER_AGENT", ""),
            "request_method":   request.method,
            "request_path":     request.path,
            "actor":            actor,
            "actor_email":      actor_email,
            "correlation_id":   correlation_id,
            "request_id":       correlation_id,
            # Frontend audit context headers (X-Client-* from audit-headers.ts)
            "client_device_id": request.META.get("HTTP_X_DEVICE_ID"),
            "client_timezone":  request.META.get("HTTP_X_CLIENT_TIMEZONE"),
            "client_locale":    request.META.get("HTTP_X_CLIENT_LOCALE"),
            "client_platform":  request.META.get("HTTP_X_CLIENT_PLATFORM"),
            "client_geo_lat":   request.META.get("HTTP_X_CLIENT_GEO_LAT"),
            "client_geo_lng":   request.META.get("HTTP_X_CLIENT_GEO_LNG"),
            "client_geo_acc":   request.META.get("HTTP_X_CLIENT_GEO_ACCURACY"),
            # Phase 9: 2026 compliance fields injected into context at entry point
            "session_fingerprint": request.META.get("HTTP_X_SESSION_FINGERPRINT"),
            "tls_version":         (
                request.META.get("SSL_PROTOCOL")
                or request.META.get("HTTP_X_FORWARDED_PROTO_VERSION")
            ),
            "api_version":         _extract_api_version(request.path),
            "request_size_bytes":  _safe_content_length(request),
        }
        # Inject correlation ID onto the request for downstream view access
        request.correlation_id = correlation_id
        request.request_id = correlation_id
        return ctx, correlation_id

    # ── Fire-and-forget dispatchers ───────────────────────────────────────────
    def _maybe_capture_failed_asgi(self, request, response, correlation_id: str) -> None:
        """
        Dispatch an audit event for 4xx/5xx responses — ASGI fire-and-forget.

        Uses asyncio.get_running_loop().create_task() (preferred over
        get_event_loop() which is deprecated in Python 3.10+) so the event
        is enqueued on the running event loop but processed AFTER the HTTP
        response has been sent. The response path is completely non-blocking.

        Args:
            request: Django HttpRequest.
            response: Django HttpResponse.
            correlation_id: Correlation ID string.
        """
        if not self._should_capture(request, response):
            return
        ctx = _audit_ctx.get()
        payload = self._build_capture_payload(request, response, correlation_id, ctx)
        try:
            loop = asyncio.get_running_loop()
            loop.create_task(_async_dispatch_audit(payload))
        except RuntimeError:
            # No running event loop (e.g. tests) — fall back to daemon thread
            self._dispatch_in_daemon_thread(payload)

    def _maybe_capture_failed_wsgi(self, request, response, correlation_id: str) -> None:
        """
        Dispatch an audit event for 4xx/5xx responses — WSGI daemon thread.

        Spawns a daemon thread that calls AuditService.log() so the response
        is returned to the client immediately without waiting for the DB write.

        Args:
            request: Django HttpRequest.
            response: Django HttpResponse.
            correlation_id: Correlation ID string.
        """
        if not self._should_capture(request, response):
            return
        ctx = _audit_ctx.get()
        payload = self._build_capture_payload(request, response, correlation_id, ctx)
        self._dispatch_in_daemon_thread(payload)

    @staticmethod
    def _should_capture(request, response) -> bool:
        """Return True if this response should generate an automatic audit event."""
        if response.status_code < 400:
            return False
        if request.method in _AUTO_CAPTURE_EXEMPT_METHODS:
            return False
        if any(request.path.startswith(p) for p in _AUTO_CAPTURE_EXEMPT_PREFIXES):
            return False
        # Don't audit unauthenticated 401s on non-API, non-admin paths (pure noise)
        if response.status_code == 401 and not request.path.startswith(("/api/", "/admin/")):
            return False
        return True

    @staticmethod
    def _build_capture_payload(request, response, correlation_id: str, ctx: dict) -> dict:
        """
        Build the serializable audit payload from request, response and context.

        All values are plain Python scalars — safe to pass across thread/task
        boundaries without pickling issues.

        Args:
            request: Django HttpRequest.
            response: Django HttpResponse.
            correlation_id: Correlation ID string.
            ctx: Current ContextVar audit context dict.

        Returns:
            dict: Audit event payload ready for AuditService.log().
        """
        if response.status_code >= 500:
            event_type_key = "SYSTEM_ERROR"
            event_category_key = "SYSTEM"
            severity_key = "ERROR"
        elif response.status_code in (401, 403):
            event_type_key = "API_CALL"
            event_category_key = "SECURITY"
            severity_key = "WARNING"
        else:
            event_type_key = "API_CALL"
            event_category_key = "SYSTEM"
            severity_key = "WARNING"

        actor = ctx.get("actor")
        actor_id = getattr(actor, "pk", None)

        # Phase 9: capture response size from Content-Length header (best-effort)
        resp_size: int | None = None
        try:
            cl = response.get("Content-Length") or response.get("content-length")
            if cl:
                resp_size = int(cl)
        except (TypeError, ValueError):
            pass

        return {
            "event_type_key":      event_type_key,
            "event_category_key":  event_category_key,
            "severity_key":        severity_key,
            "action":              f"API {request.method} {request.path} → {response.status_code}",
            "actor_id":            str(actor_id) if actor_id else None,
            "actor_email":         ctx.get("actor_email"),
            "ip_address":          ctx.get("ip_address"),
            "user_agent":          request.META.get("HTTP_USER_AGENT", ""),
            "request_method":      request.method,
            "request_path":        request.path,
            "response_status":     response.status_code,
            "correlation_id":      correlation_id,
            "is_compliance":       response.status_code >= 500,
            # Phase 9 fields — auto-extracted at the middleware layer
            "request_size_bytes":  ctx.get("request_size_bytes"),
            "response_size_bytes": resp_size,
            "tls_version":         ctx.get("tls_version"),
            "session_fingerprint": ctx.get("session_fingerprint"),
            "api_version":         ctx.get("api_version"),
            "metadata": {
                "auto_captured": True,
                "correlation_id": correlation_id,
            },
        }

    @staticmethod
    def _dispatch_in_daemon_thread(payload: dict) -> None:
        """
        Dispatch audit log in a daemon thread (WSGI fire-and-forget).

        Daemon=True ensures the thread never blocks Django's shutdown.

        Args:
            payload: Audit payload dict built by _build_capture_payload.
        """
        def _target():
            try:
                _sync_dispatch_audit(payload)
            except Exception:
                pass  # Audit failure must never propagate
        threading.Thread(target=_target, daemon=True).start()


# ─────────────────────────────────────────────────────────────────────────────
# Async / sync audit dispatchers (called off the request path)
# ─────────────────────────────────────────────────────────────────────────────

async def _async_dispatch_audit(payload: dict) -> None:
    """
    Async fire-and-forget audit dispatch.

    Runs in the asyncio event loop after the HTTP response has been sent.
    All exceptions are swallowed — audit failure must NEVER affect users.

    Args:
        payload: Serializable audit payload dict.
    """
    try:
        from apps.audit_logs.tasks import write_audit_event
        # Dispatch to Celery — returns immediately (Redis LPUSH)
        write_audit_event.apply_async(
            kwargs={"payload": payload},
            retry=False,
            ignore_result=True,
        )
    except Exception:
        pass  # Never propagate


def _sync_dispatch_audit(payload: dict) -> None:
    """
    Sync audit dispatch — called from WSGI daemon thread.

    Runs in a background thread so the response path is not blocked.
    All exceptions are swallowed — audit failure must NEVER affect users.

    Args:
        payload: Serializable audit payload dict.
    """
    try:
        from apps.audit_logs.tasks import write_audit_event
        write_audit_event.apply_async(
            kwargs={"payload": payload},
            retry=False,
            ignore_result=True,
        )
    except Exception:
        pass  # Never propagate
