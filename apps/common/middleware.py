# apps/common/middleware.py
"""
Production-grade Django ASGI + WSGI dual-mode middleware.

DUAL-MODE ARCHITECTURE (Django 6.0 compatible)
==============================================
Every middleware class supports BOTH deployment modes simultaneously:

  ASGI (Uvicorn / Daphne)
  ───────────────────────
  Django's ASGI handler calls asyncio.iscoroutinefunction(middleware.__call__)
  which returns True because we use asgiref.sync.markcoroutinefunction().
  The handler awaits __call__ directly on the event loop — zero thread-pool
  handoffs, minimum latency.

  WSGI (manage.py runserver / gunicorn)
  ──────────────────────────────────────
  Django's WSGI handler calls middleware.__call__(request) synchronously.
  Since async def under a synchronous WSGI handler would return an unawaited
  coroutine, we define both __call__ (sync) and __acall__ (async) so each
  handler picks the right entry point automatically.

  The pattern:
      __call__  = sync entry point (WSGI)
      __acall__ = async entry point (ASGI)

  Django ≥ 3.1 checks for __acall__ before falling back to __call__, so:
  - ASGI handler: sees __acall__ → awaits it in event loop ✓
  - WSGI handler: calls __call__ synchronously ✓

MIDDLEWARE STACK (register in this order in settings.py)::

    MIDDLEWARE = [
        'apps.common.middleware.RequestIDMiddleware',
        'apps.common.middleware.RequestTimingMiddleware',
        'apps.common.middleware.SecurityAuditMiddleware',
        ...
    ]
"""

import asyncio
import hashlib
import logging
import time
import uuid

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

logger = logging.getLogger('application')
security_logger = logging.getLogger('security')


# ================================================================
# 1. REQUEST ID INJECTION  (dual WSGI + ASGI)
# ================================================================

class RequestIDMiddleware:
    """
    Inject a unique UUID4 ``X-Request-ID`` into every request / response.

    Works under both WSGI (``manage.py runserver``, gunicorn) and ASGI
    (Uvicorn, Daphne) without any performance penalty in either mode.

    The request ID is:
        • Read from the incoming ``X-Request-ID`` header if present — allows
          distributed tracing from load balancers / mobile SDKs.
        • Generated as UUID4 if not present.
        • Stored on ``request.request_id`` for views, serializers, logs.
        • Added to the response ``X-Request-ID`` header for client correlation.
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        # Tell Django's ASGI handler "our __acall__ is the async entry point"
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        """Synchronous path — WSGI (manage.py runserver / gunicorn)."""
        request_id = (
            request.headers.get('X-Request-Id')
            or request.headers.get('X-Request-ID')
            or str(uuid.uuid4())
        )
        request.request_id = request_id
        response = self.get_response(request)
        response['X-Request-ID'] = request_id
        return response

    async def __acall__(self, request):
        """Asynchronous path — ASGI (Uvicorn / Daphne). Zero thread overhead."""
        request_id = (
            request.headers.get('X-Request-Id')
            or request.headers.get('X-Request-ID')
            or str(uuid.uuid4())
        )
        request.request_id = request_id
        response = await self.get_response(request)
        response['X-Request-ID'] = request_id
        return response


# ================================================================
# 2. REQUEST TIMING  (dual WSGI + ASGI)
# ================================================================

class RequestTimingMiddleware:
    """
    Log method, path, status code, and wall-clock time (ms) for every request.

    Output format::

        [GET] /api/v2/products/ → 200 in 12.3ms [req=<uuid>]

    Uses ``time.monotonic()`` which is event-loop-safe and thread-safe.
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        """Synchronous path — WSGI."""
        start = time.monotonic()
        response = self.get_response(request)
        self._emit_log(request, response, start)
        return response

    async def __acall__(self, request):
        """Asynchronous path — ASGI."""
        start = time.monotonic()
        response = await self.get_response(request)
        self._emit_log(request, response, start)
        return response

    def _emit_log(self, request, response, start: float) -> None:
        duration_ms = (time.monotonic() - start) * 1000
        request_id = getattr(request, 'request_id', '-')
        # QueueHandler (wired in apps.py) makes this call return in nanoseconds
        logger.info(
            "[%s] %s \u2192 %d in %.1fms [req=%s]",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            request_id,
        )
        response['X-Response-Time'] = f"{duration_ms:.1f}ms"


# ================================================================
# 3. SECURITY AUDIT — pure helper functions (no I/O)
# ================================================================

def _get_client_ip(request) -> str:
    """
    Extract the real client IP address.

    Checks ``X-Forwarded-For`` first (Nginx / Cloudflare / load balancer),
    then falls back to ``REMOTE_ADDR``. Only leftmost XFF IP is used.
    Pure header read — zero I/O, safe in both sync and async contexts.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _get_device_id(request) -> str:
    """
    Extract or derive a stable device identifier.

    Priority:
    1. ``X-Device-ID`` header — sent by mobile / desktop clients explicitly.
    2. ``X-Fingerprint`` header — pre-computed fingerprint from some SDKs.
    3. SHA-256(User-Agent + IP) — stable for same browser/IP pair.
       Prefixed with ``fp:`` in logs so consumers know it is derived.

    Stores result on ``request.device_id`` for downstream view access.
    Pure CPU + header reads — zero I/O, safe in any context.
    """
    explicit = (
        request.headers.get('X-Device-ID')
        or request.headers.get('X-Fingerprint')
    )
    if explicit:
        request.device_id = str(explicit)[:64]
        return request.device_id

    ua = request.META.get('HTTP_USER_AGENT', '')
    ip = _get_client_ip(request)
    fingerprint = hashlib.sha256(
        f"{ua}|{ip}".encode()
    ).hexdigest()[:20]
    request.device_id = f'fp:{fingerprint}'
    return request.device_id


def _get_user_context(request) -> tuple:
    """
    Safely extract (user_id, role) from the request.

    Returns:
        tuple[str, str]: (user_id, user_role)
    """
    try:
        user = getattr(request, 'user', None)
        if user is None or not user.is_authenticated:
            return 'anonymous', 'anonymous'
        uid = str(getattr(user, 'pk', '?'))
        role = getattr(user, 'role', None) or (
            'superadmin' if getattr(user, 'is_superuser', False)
            else 'staff' if getattr(user, 'is_staff', False)
            else 'authenticated'
        )
        return uid, role
    except Exception:  # noqa: BLE001
        return 'unknown', 'unknown'


def _get_session_cookie(request) -> str:
    """
    Return the first 16 chars of the session COOKIE — NOT from the DB.

    CRITICAL PERFORMANCE NOTE:
        ``request.session.session_key`` triggers a synchronous database read.
        Under ASGI this would block the event loop. Instead, we read the raw
        ``sessionid`` cookie — pure string operation, zero I/O, same audit
        trail value (the opaque session token held by the client).
    """
    raw = request.COOKIES.get('sessionid', '')
    return raw[:16] if raw else '-'


# ================================================================
# 3. SECURITY AUDIT MIDDLEWARE  (dual WSGI + ASGI)
# ================================================================

class SecurityAuditMiddleware:
    """
    Production security audit log — records every HTTP interaction.

    Every request through the Fashionistar API is recorded with:

    ┌─────────────────────────────────────────────────────────────┐
    │ Field           │ Source                                    │
    ├─────────────────┼───────────────────────────────────────────┤
    │ request_id      │ X-Request-ID header (middleware 1)        │
    │ device_id       │ X-Device-ID header or UA+IP fingerprint   │
    │ session_cookie  │ sessionid cookie (first 16 chars, no DB)  │
    │ client_ip       │ X-Forwarded-For → REMOTE_ADDR             │
    │ method          │ request.method                            │
    │ path            │ request.get_full_path() (incl. ?query)    │
    │ status          │ HTTP response status code                 │
    │ duration_ms     │ Wall-clock time in milliseconds           │
    │ user_id         │ request.user.pk or 'anonymous'            │
    │ role            │ user.role / superadmin / staff / anon     │
    │ user_agent      │ HTTP_USER_AGENT (first 300 chars)         │
    │ referrer        │ HTTP_REFERER header                       │
    └─────────────────┴───────────────────────────────────────────┘

    PERFORMANCE:
      • ASGI: runs directly on the event loop via __acall__ — zero threads.
      • WSGI: runs synchronously via __call__ — normal Django runserver path.
      • All attribute reads are in-memory — zero additional I/O.
      • Log emission via QueueHandler (apps.py) returns in nanoseconds.

    Log levels:
        INFO    — 2xx, 3xx (normal traffic)
        WARNING — 401, 403 (auth/permission failures)
        ERROR   — 5xx (server errors)
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        """Synchronous path — WSGI (manage.py runserver / gunicorn)."""
        # Resolve device_id early so views can read request.device_id
        _get_device_id(request)

        start = time.monotonic()
        response = self.get_response(request)
        self._emit_audit(request, response, start)
        return response

    async def __acall__(self, request):
        """Asynchronous path — ASGI (Uvicorn / Daphne)."""
        _get_device_id(request)

        start = time.monotonic()
        response = await self.get_response(request)
        self._emit_audit(request, response, start)
        return response

    def _emit_audit(self, request, response, start: float) -> None:
        """Shared audit log emission — pure CPU + QueueHandler enqueue."""
        duration_ms = (time.monotonic() - start) * 1000
        status_code = response.status_code

        client_ip = _get_client_ip(request)
        user_id, role = _get_user_context(request)
        request_id = getattr(request, 'request_id', '-')
        session = _get_session_cookie(request)
        device_id = getattr(request, 'device_id', '-')
        path = request.get_full_path()
        ua = request.META.get('HTTP_USER_AGENT', '-')[:300]
        referrer = request.META.get('HTTP_REFERER', '-')[:200]

        if status_code in (401, 403):
            action = 'PERMISSION_DENIED'
        elif status_code >= 500:
            action = 'SERVER_ERROR'
        elif status_code >= 400:
            action = 'CLIENT_ERROR'
        else:
            action = 'REQUEST'

        msg = (
            "SECURITY_AUDIT action=%s req=%s device=%s session=%s "
            "ip=%s method=%s path=%s status=%d duration_ms=%.1f "
            "user_id=%s role=%s ua=%r referrer=%s"
        ) % (
            action, request_id, device_id, session,
            client_ip, request.method, path, status_code,
            duration_ms, user_id, role, ua, referrer,
        )

        if status_code >= 500:
            security_logger.error(msg)
        elif status_code in (401, 403):
            security_logger.warning(msg)
        else:
            security_logger.info(msg)
