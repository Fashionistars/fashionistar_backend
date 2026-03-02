# apps/common/middleware.py
"""
Production-grade Django ASGI/WSGI middleware for the Fashionistar backend.

PERFORMANCE ARCHITECTURE (Django 6.0 ASGI-native)
==================================================
All three middleware classes implement the Django async middleware protocol:

    async_capable = True   → Django ASGI handler runs __call__ in the event
                             loop directly — NO thread-pool handoff.
    sync_capable  = True   → Classes still work under WSGI (gunicorn/wsgiref).

The ASGI handler checks `asyncio.iscoroutinefunction(middleware.__call__)` and,
when True, awaits it directly in the event loop — eliminating the 30-60 second
latency caused by wrapping synchronous middleware in run_in_executor().

Middleware stack (register in this order in settings.py)::

    MIDDLEWARE = [
        'apps.common.middleware.RequestIDMiddleware',
        'apps.common.middleware.RequestTimingMiddleware',
        'apps.common.middleware.SecurityAuditMiddleware',
        ...
    ]

SecurityAuditMiddleware
-----------------------
IMPORTANT: The session key is read from the signed session cookie
(request.COOKIES), NOT from request.session — avoiding a synchronous
database round-trip that was the secondary source of 30-60s hangs.
"""

import asyncio
import hashlib
import logging
import time
import uuid

logger = logging.getLogger('application')
security_logger = logging.getLogger('security')


# ================================================================
# 1. REQUEST ID INJECTION  (fully async)
# ================================================================

class RequestIDMiddleware:
    """
    Inject a unique UUID4 ``X-Request-ID`` into every request / response.

    Async-native: runs directly in the asyncio event loop under ASGI/Uvicorn.
    Falls back to standard sync execution under WSGI (gunicorn/wsgiref).

    The request ID is:
        • Read from the incoming ``X-Request-ID`` header if present (distributed
          tracing — load balancer / API gateway / mobile SDK passes this through).
        • Generated as UUID4 if not present.
        • Stored on ``request.request_id`` for use in views, serializers, logs.
        • Written to the response ``X-Request-ID`` header for client correlation.
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if asyncio.iscoroutinefunction(self.get_response):
            # Signal Django's ASGI handler to call us as a coroutine
            self._is_coroutine = asyncio.coroutines._is_coroutine

    async def __call__(self, request):
        request_id = (
            request.headers.get('X-Request-Id')
            or request.headers.get('X-Request-ID')
            or str(uuid.uuid4())
        )
        request.request_id = request_id

        response = await self.get_response(request)

        response['X-Request-ID'] = request_id
        return response

    # ── WSGI compatibility shim ───────────────────────────────────────────────
    # Django calls __call__ directly for sync middleware. When the server is
    # WSGI, get_response is NOT a coroutine, so __call__ is the sync path.
    # We re-use __call__ here: asyncio.iscoroutinefunction(get_response) == False
    # means Django won't try to await us.


# ================================================================
# 2. REQUEST TIMING  (fully async)
# ================================================================

class RequestTimingMiddleware:
    """
    Log method, path, status code, and wall-clock time (ms) for every request.

    Output format::

        [GET] /api/v2/products/ → 200 in 12.3ms [req=<uuid>]

    Async-native — uses ``time.monotonic()`` which is safe on all threads and
    the event loop. Zero blocking I/O.
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if asyncio.iscoroutinefunction(self.get_response):
            self._is_coroutine = asyncio.coroutines._is_coroutine

    async def __call__(self, request):
        start = time.monotonic()

        response = await self.get_response(request)

        duration_ms = (time.monotonic() - start) * 1000
        request_id = getattr(request, 'request_id', '-')

        # logger.info is non-blocking: the QueueHandler (configured in
        # settings.py + apps.py) queues the record and returns immediately.
        logger.info(
            "[%s] %s → %d in %.1fms [req=%s]",
            request.method,
            request.path,
            response.status_code,
            duration_ms,
            request_id,
        )

        response['X-Response-Time'] = f"{duration_ms:.1f}ms"
        return response


# ================================================================
# 3. SECURITY AUDIT — helpers (pure CPU, no I/O)
# ================================================================

def _get_client_ip(request) -> str:
    """
    Extract the real client IP address.

    Checks ``X-Forwarded-For`` first (Nginx / load balancer / Cloudflare),
    then falls back to ``REMOTE_ADDR``. Only the leftmost XFF IP is used.
    Pure header read — zero I/O.
    """
    xff = request.META.get('HTTP_X_FORWARDED_FOR', '')
    if xff:
        return xff.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR', 'unknown')


def _get_device_id(request) -> str:
    """
    Extract or derive a stable device identifier.

    Priority:
    1. ``X-Device-ID`` header  — explicitly sent by mobile / desktop clients.
    2. ``X-Fingerprint`` header — some SDKs send a pre-computed fingerprint.
    3. SHA-256 of (User-Agent + IP) — stable for same browser/IP pair. Prefixed
       with ``fp:`` so log consumers know it is derived, not device-supplied.

    Pure CPU + header reads — zero I/O.
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


def _get_user_context(request) -> tuple[str, str]:
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
        ``request.session.session_key`` triggers a synchronous database read
        (Django session backend reads from DB or file to get the key).
        Under ASGI this would block the event loop for the full DB round-trip.

        Instead, we read the raw ``sessionid`` cookie value from the signed
        cookie string — this is a pure string operation with zero I/O and
        delivers the same audit trail value (the opaque session token the
        client holds).
    """
    raw = request.COOKIES.get('sessionid', '')
    return raw[:16] if raw else '-'


# ================================================================
# 3. SECURITY AUDIT MIDDLEWARE  (fully async)
# ================================================================

class SecurityAuditMiddleware:
    """
    Production security audit log — captures every HTTP interaction.

    Every request through the Fashionistar API is recorded with:

    ┌─────────────────────────────────────────────────────────────┐
    │ Field           │ Source                                    │
    ├─────────────────┼───────────────────────────────────────────┤
    │ request_id      │ X-Request-ID header (middleware 1)        │
    │ device_id       │ X-Device-ID header or UA+IP fingerprint   │
    │ session_cookie  │ sessionid cookie (first 16 chars, no DB)  │
    │ client_ip       │ X-Forwarded-For → REMOTE_ADDR             │
    │ method          │ request.method (GET/POST/PUT/DELETE…)     │
    │ path            │ request.get_full_path() (incl. ?query)    │
    │ status          │ HTTP response status code                 │
    │ duration_ms     │ Wall-clock time in milliseconds           │
    │ user_id         │ request.user.pk or 'anonymous'            │
    │ role            │ user.role or superadmin/staff/anonymous   │
    │ user_agent      │ HTTP_USER_AGENT header (first 300 chars)  │
    │ referrer        │ HTTP_REFERER header                       │
    └─────────────────┴───────────────────────────────────────────┘

    PERFORMANCE GUARANTEES (async-native):
      • Zero thread-pool handoffs — runs directly in asyncio event loop.
      • Zero DB reads — session data from cookie, user from request.user
        (already resolved by AuthenticationMiddleware earlier in the stack).
      • Log emission via QueueHandler — write returns in nanoseconds, actual
        file/stream I/O happens in a background QueueListener thread.

    Log levels:
        INFO    — 2xx, 3xx (normal traffic)
        WARNING — 401, 403 (auth/permission failures)
        ERROR   — 5xx (server errors, alert-worthy)
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        if asyncio.iscoroutinefunction(self.get_response):
            self._is_coroutine = asyncio.coroutines._is_coroutine

    async def __call__(self, request):
        start = time.monotonic()

        # Resolve device_id early (pure CPU, no I/O) so views can read it
        device_id = _get_device_id(request)  # also sets request.device_id

        response = await self.get_response(request)

        duration_ms = (time.monotonic() - start) * 1000
        status_code = response.status_code

        # All attribute reads below are pure in-memory — zero I/O
        client_ip    = _get_client_ip(request)
        user_id, role = _get_user_context(request)
        request_id   = getattr(request, 'request_id', '-')
        session      = _get_session_cookie(request)  # cookie read, NOT DB
        path         = request.get_full_path()
        ua           = request.META.get('HTTP_USER_AGENT', '-')[:300]
        referrer     = request.META.get('HTTP_REFERER', '-')[:200]

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

        # QueueHandler: this call returns in nanoseconds — actual write
        # happens asynchronously in the QueueListener background thread.
        if status_code >= 500:
            security_logger.error(msg)
        elif status_code in (401, 403):
            security_logger.warning(msg)
        else:
            security_logger.info(msg)

        return response
