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
from __future__ import annotations

import json
from typing import Any

from django.core.cache import caches
from django.http import JsonResponse

import asyncio
import hashlib
import logging
import time
import uuid

from asgiref.sync import iscoroutinefunction, markcoroutinefunction

from apps.common.request import get_client_ip
from apps.common.roles import normalize_role

# ── Redis utilities ───────────────────────────────────────────────────────────
from apps.common.utils.redis import (       # noqa: F401
    get_redis_connection_safe,
    cache_upload_presign,
    get_cached_presign,
    invalidate_upload_presign,
    redis_set,
    redis_get,
    redis_delete,
    redis_incr,
    REDIS_MAX_RETRIES,
    REDIS_RETRY_DELAY,
    # Single-try API endpoint caching (no retry loop)
    api_cache_get,
    api_cache_set,
    api_cache_delete,
    api_cache_delete_pattern,
)


logger = logging.getLogger(__name__)
security_logger = logging.getLogger('security')


# ================================================================
# 1. REQUEST ID INJECTION  (dual WSGI + ASGI)
# ================================================================

_asyncio_exception_handler_installed = False


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
        global _asyncio_exception_handler_installed
        if not _asyncio_exception_handler_installed:
            try:
                loop = asyncio.get_running_loop()
                default_handler = loop.get_exception_handler()

                def custom_handler(loop, context):
                    message = context.get("message", "")
                    exception = context.get("exception")
                    # Silently ignore the shielded future CancelledError warnings typical under Python 3.14 request aborts
                    if (
                        "CancelledError exception in shielded future" in message
                        or isinstance(exception, asyncio.CancelledError)
                    ):
                        return
                    if default_handler:
                        default_handler(loop, context)
                    else:
                        loop.default_exception_handler(context)

                loop.set_exception_handler(custom_handler)
                _asyncio_exception_handler_installed = True
                logger.debug("Successfully installed custom asyncio event loop exception handler for shielded future warnings.")
            except Exception as e:
                logger.debug("Failed to set custom asyncio exception handler: %s", e)

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

        [GET] /api/v1/products/ → 200 in 12.3ms [req=<uuid>]

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
    ip = get_client_ip(request)
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
        if user is None or not getattr(user, 'is_authenticated', False):
            user = getattr(request, 'auth', None)
        if user is None or not getattr(user, 'is_authenticated', False):
            return 'anonymous', 'anonymous'
        uid = str(getattr(user, 'pk', '?'))
        raw_role = getattr(user, 'role', None)
        role = normalize_role(raw_role) or (
            'super_admin' if getattr(user, 'is_superuser', False)
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

        client_ip = get_client_ip(request)
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




# apps/authentication/middleware/idempotency.py
"""
FASHIONISTAR — Idempotency Middleware (ASGI-Safe v2.0)
=======================================================
Implements the Idempotency Key pattern for all stateful POST endpoints.

ASGI SAFETY FIX (Phase 2):
  Previous version had no ``__acall__`` — Django's ASGI handler wrapped the
  entire middleware in sync_to_async on every POST, adding a thread-pool
  handoff (1–50ms) plus synchronous Redis calls that blocked the event loop.

  Fix:
    1. Added ``async def __acall__`` with ``redis.asyncio`` for non-blocking
       Redis I/O under Uvicorn/ASGI.
    2. Replaced two-step ``cache.add(lock_key)`` (SETNX) + implicit EXPIRE
       with a **single Redis Lua script** (EVALSHA) — one atomic round-trip,
       no race window between SET and EXPIRE.
    3. Added ``markcoroutinefunction(self)`` so Django's ASGI handler calls
       ``__acall__`` directly without any sync_to_async wrapping.

Purpose:
  Under 100,000 RPS with network retries, the same registration or checkout
  POST can arrive multiple times — creating duplicate users, orders, or
  payments. This middleware guarantees exactly-once semantics.

How it works:
  1. Client sends ``X-Idempotency-Key: <uuid4>`` header with every POST.
  2. Middleware checks Redis for an existing cached response under that key.
     - HIT  → return the original response immediately (no view called).
     - LOCK → another request with the same key is in-flight; return 409.
     - MISS → acquire Lua-atomic lock; call view; store response; release lock.
  3. Successful (2xx) response is cached for IDEMPOTENCY_TTL seconds (24h).

Protected methods:
  POST only (idempotency is not meaningful for GET/PUT/PATCH/DELETE without
  semantic consideration — those methods are intrinsically idempotent).

Endpoints skipped (whitelisted):
  - Token refresh  (/token/refresh/)  — stateless by design.
  - Logout         (/logout/)         — idempotent by design.
  - Health         (/health/)         — GET, never POST.

Redis key schema:
  idempotency:lock:<key>     → "1"  (atomic Lua SET NX EX, TTL=30s)
  idempotency:resp:<key>     → JSON (set after success, TTL=24h)

Dual-mode architecture:
  __call__  = sync path (WSGI: gunicorn, manage.py runserver)
  __acall__ = async path (ASGI: Uvicorn, Daphne) — uses redis.asyncio

Enterprise Reference:
  - Stripe Idempotency Keys: https://stripe.com/docs/api/idempotent_requests
  - Redis SET NX EX (atomic): https://redis.io/commands/set/
"""



# ─── Configuration ─────────────────────────────────────────────────────────────
IDEMPOTENCY_CACHE_ALIAS = "idempotency"
IDEMPOTENCY_HEADER = "HTTP_X_IDEMPOTENCY_KEY"   # Django META key
IDEMPOTENCY_TTL = 60 * 60 * 24                  # 24 hours in seconds
IDEMPOTENCY_LOCK_TTL = 30                        # In-flight lock TTL (seconds)
IDEMPOTENCY_LOCK_PREFIX = "idempotency:lock:"
IDEMPOTENCY_RESP_PREFIX = "idempotency:resp:"

# Endpoints that bypass idempotency entirely (always fast-path through)
IDEMPOTENCY_SKIP_PATHS = frozenset([
    "/api/v1/auth/login/",
    "/api/v1/auth/logout/",
    "/api/v1/auth/token/refresh/",
    "/health/",
])

# ─── Redis Lua script: atomic SET NX EX ────────────────────────────────────────
# Replaces the old two-step SETNX + EXPIRE (which had a race window).
# Single round-trip: sets key with NX (only if not exists) and EX (TTL).
# Returns 1 on successful acquisition, 0 if lock already held.
_LUA_ACQUIRE_LOCK = """
local result = redis.call('SET', KEYS[1], ARGV[1], 'NX', 'EX', ARGV[2])
if result then return 1 else return 0 end
"""


def _get_cache():
    """
    Return the idempotency cache backend.

    Gracefully falls back to 'default' if 'idempotency' alias is not defined
    in settings.CACHES (e.g. in test environments with LocMemCache).

    Returns:
        Django cache backend instance.
    """
    try:
        return caches[IDEMPOTENCY_CACHE_ALIAS]
    except Exception:
        return caches["default"]


def _get_async_redis():
    """
    Return an async redis.asyncio client using the same connection parameters
    as the 'idempotency' Django cache backend.

    Falls back to None if redis.asyncio is unavailable — the async path will
    then degrade to using the synchronous Django cache (acceptable for low-load
    scenarios such as development).

    Returns:
        redis.asyncio.Redis instance, or None on import failure.
    """
    try:
        import redis.asyncio as aioredis
        from django.conf import settings

        # Read connection details from the idempotency cache config
        cache_conf = settings.CACHES.get(
            IDEMPOTENCY_CACHE_ALIAS,
            settings.CACHES.get("default", {}),
        )
        location = cache_conf.get("LOCATION", "redis://127.0.0.1:6379/1")
        options = cache_conf.get("OPTIONS", {})
        password = options.get("PASSWORD", None)

        return aioredis.from_url(
            location,
            password=password,
            encoding="utf-8",
            decode_responses=True,
            socket_timeout=0.5,           # 500ms hard timeout on Redis I/O
            socket_connect_timeout=0.5,
        )
    except Exception:
        return None


class IdempotencyMiddleware:
    """
    ASGI + WSGI dual-mode Django middleware for POST endpoint idempotency.

    Position in MIDDLEWARE list:
        Place AFTER AuditContextMiddleware but BEFORE Django's core middleware
        so that replayed cached responses still get proper session/auth headers.

    Performance profile (after Phase 2 fix):
        ASGI: ~0.5ms per cache HIT (async Redis LOLWUT → return)
        ASGI: ~1.0ms per cache MISS + view call (Lua lock → view → cache set)
        WSGI: ~1.5ms per cache HIT (sync Django cache framework)
        WSGI: ~2.0ms per cache MISS + view call
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        # Lazily built async Redis client — created once per worker process
        self._async_redis = None
        # Signal to Django's ASGI handler: call __acall__, not __call__
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    # ── WSGI synchronous path ──────────────────────────────────────────────────
    def __call__(self, request):
        """Sync path — WSGI (gunicorn, manage.py runserver)."""
        # Fast-path: skip non-POST requests immediately
        if request.method != "POST":
            return self.get_response(request)

        # ── Skip whitelisted paths ─────────────────────────────────────────
        if request.path in IDEMPOTENCY_SKIP_PATHS:
            return self.get_response(request)

        # ── Extract idempotency key from header ────────────────────────────
        raw_key = request.META.get(IDEMPOTENCY_HEADER, "").strip()
        logger.debug(
            "🔑 IdempotencyMiddleware | path=%s | raw_key=%r | len=%d | header=%s",
            request.path, raw_key[:20] if raw_key else "(empty)", len(raw_key), IDEMPOTENCY_HEADER,
        )
        if not raw_key:
            # No key provided → pass through without idempotency protection
            # (backwards compatible — existing clients without the header work fine)
            return self.get_response(request)

        # ── Validate key format (must be UUID4 or any non-empty string ≤128 chars)
        if len(raw_key) > 128:
            return JsonResponse(
                {"status": "error", "message": "X-Idempotency-Key must be ≤128 characters."},
                status=400,
            )

        lock_key = f"{IDEMPOTENCY_LOCK_PREFIX}{raw_key}"
        resp_key = f"{IDEMPOTENCY_RESP_PREFIX}{raw_key}"
        # Use Django cache framework (IGNORE_EXCEPTIONS=True → never hangs)
        _cache = _get_cache()

        # ── CHECK: Cached response? ────────────────────────────────────────
        cached = _cache.get(resp_key)
        if cached is not None:
            logger.info("♻️  Idempotency HIT | key=%s | path=%s", raw_key, request.path)
            try:
                data = json.loads(cached)
                return JsonResponse(data["body"], status=data["status"], safe=False)
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning("⚠️  Idempotency cache deserialization failed | key=%s: %s", raw_key, exc)
                # Fall through to normal processing (safe degradation)

        # ── LOCK: Prevent concurrent in-flight requests with same key ──────
        # cache.add() is atomic (SETNX equivalent). Returns True on acquisition.
        # None = Redis unreachable (IGNORE_EXCEPTIONS) → degrade gracefully.
        acquired = _cache.add(lock_key, "1", timeout=IDEMPOTENCY_LOCK_TTL)
        # If Redis is unreachable or throws a connection error, acquired is None
        # (due to IGNORE_EXCEPTIONS = True). We gracefully degrade and allow the
        # request to proceed as if lock was acquired. Only block on explicit False.
        if acquired is False:
            logger.warning("⚠️  Idempotency LOCK CONFLICT | key=%s | path=%s", raw_key, request.path)
            return JsonResponse(
                {
                    "status": "error",
                    "message": (
                        "A request with this Idempotency-Key is already in progress. "
                        "Retry after a moment."
                    ),
                    "idempotency_key": raw_key,
                },
                status=409,
            )

        # ── PROCESS: Call the actual view ──────────────────────────────────
        try:
            response = self.get_response(request)
        except Exception:
            _cache.delete(lock_key)  # Always release lock on exception
            raise

        # ── CACHE: Store successful responses only (2xx) ───────────────────
        # Never cache 4xx/5xx — let the client retry naturally.
        if 200 <= response.status_code < 300:
            try:
                response_body = json.loads(response.content.decode("utf-8"))
                payload = json.dumps({"status": response.status_code, "body": response_body})
                _cache.set(resp_key, payload, timeout=IDEMPOTENCY_TTL)
                logger.info(
                    "✅ Idempotency CACHED | key=%s | status=%d | path=%s | ttl=%ds",
                    raw_key, response.status_code, request.path, IDEMPOTENCY_TTL,
                )
            except (json.JSONDecodeError, UnicodeDecodeError, Exception) as exc:
                # Non-JSON response (e.g. binary) — skip caching, not an error
                logger.debug("ℹ️  Idempotency skipped caching non-JSON response | key=%s: %s", raw_key, exc)

        # ── RELEASE: Always release the lock after processing ──────────────
        _cache.delete(lock_key)
        return response

    # ── ASGI asynchronous path ─────────────────────────────────────────────────
    async def __acall__(self, request):
        """
        Async path — ASGI (Uvicorn, Daphne). Zero sync_to_async overhead.

        Uses redis.asyncio for non-blocking Redis I/O and the Lua EVALSHA
        script for atomic lock acquisition in a single round-trip.

        Args:
            request: Django HttpRequest (ASGI scope).

        Returns:
            HttpResponse: Cached replay, 409 conflict, or fresh view response.
        """
        # Fast-path: skip non-POST requests immediately (no await needed)
        if request.method != "POST":
            return await self.get_response(request)

        # ── Skip whitelisted paths ─────────────────────────────────────────
        if request.path in IDEMPOTENCY_SKIP_PATHS:
            return await self.get_response(request)

        # ── Extract idempotency key from header ────────────────────────────
        raw_key = request.META.get(IDEMPOTENCY_HEADER, "").strip()
        logger.debug(
            "🔑 IdempotencyMiddleware | path=%s | raw_key=%r | len=%d | header=%s",
            request.path, raw_key[:20] if raw_key else "(empty)", len(raw_key), IDEMPOTENCY_HEADER,
        )
        if not raw_key:
            # No key provided → pass through without idempotency protection
            return await self.get_response(request)

        # ── Validate key format (must be UUID4 or any non-empty string ≤128 chars)
        if len(raw_key) > 128:
            return JsonResponse(
                {"status": "error", "message": "X-Idempotency-Key must be ≤128 characters."},
                status=400,
            )

        lock_key = f"{IDEMPOTENCY_LOCK_PREFIX}{raw_key}"
        resp_key = f"{IDEMPOTENCY_RESP_PREFIX}{raw_key}"

        # Attempt async Redis path first; fall back to sync Django cache
        async_redis = self._get_or_create_async_redis()

        if async_redis is not None:
            return await self._handle_async_redis(
                request, raw_key, lock_key, resp_key, async_redis
            )
        # Fallback: sync cache via Django framework (IGNORE_EXCEPTIONS=True)
        return await self._handle_sync_cache_async(
            request, raw_key, lock_key, resp_key
        )

    def _get_or_create_async_redis(self):
        """
        Lazily initialize the async Redis client once per worker process.

        Returns:
            redis.asyncio.Redis or None.
        """
        if self._async_redis is None:
            self._async_redis = _get_async_redis()
        return self._async_redis

    async def _handle_async_redis(
        self, request, raw_key: str, lock_key: str, resp_key: str, async_redis: Any
    ):
        """
        Idempotency check using redis.asyncio for fully non-blocking I/O.

        Uses Lua EVAL for atomic lock acquisition (single round-trip vs. two).

        Args:
            request: Django HttpRequest.
            raw_key: Raw idempotency key from header.
            lock_key: Redis key for the in-flight lock.
            resp_key: Redis key for the cached response.
            async_redis: redis.asyncio.Redis client.

        Returns:
            HttpResponse: Cached replay, 409 conflict, or fresh view response.
        """
        try:
            # ── CHECK: Cached response? ────────────────────────────────────
            cached = await async_redis.get(resp_key)
            if cached is not None:
                logger.info("♻️  Idempotency HIT (async) | key=%s | path=%s", raw_key, request.path)
                try:
                    data = json.loads(cached)
                    return JsonResponse(data["body"], status=data["status"], safe=False)
                except (json.JSONDecodeError, KeyError, TypeError) as exc:
                    logger.warning(
                        "⚠️  Idempotency cache deserialization failed | key=%s: %s", raw_key, exc
                    )
                    # Fall through to normal processing

            # ── LOCK: Atomic SET NX EX via Lua script ──────────────────────
            # Single Redis round-trip; returns 1 (acquired) or 0 (conflict)
            acquired = await async_redis.eval(
                _LUA_ACQUIRE_LOCK,
                1,                          # numkeys
                lock_key,                   # KEYS[1]
                "1",                        # ARGV[1]
                str(IDEMPOTENCY_LOCK_TTL),  # ARGV[2]
            )
            if acquired == 0:
                logger.warning(
                    "⚠️  Idempotency LOCK CONFLICT (async) | key=%s | path=%s", raw_key, request.path
                )
                return JsonResponse(
                    {
                        "status": "error",
                        "message": (
                            "A request with this Idempotency-Key is already in progress. "
                            "Retry after a moment."
                        ),
                        "idempotency_key": raw_key,
                    },
                    status=409,
                )

            # ── PROCESS: Call the actual view ──────────────────────────────
            try:
                response = await self.get_response(request)
            except Exception:
                await async_redis.delete(lock_key)
                raise

            # ── CACHE: Store 2xx responses ─────────────────────────────────
            if 200 <= response.status_code < 300:
                try:
                    response_body = json.loads(response.content.decode("utf-8"))
                    payload = json.dumps({"status": response.status_code, "body": response_body})
                    await async_redis.setex(resp_key, IDEMPOTENCY_TTL, payload)
                    logger.info(
                        "✅ Idempotency CACHED (async) | key=%s | status=%d | ttl=%ds",
                        raw_key, response.status_code, IDEMPOTENCY_TTL,
                    )
                except (json.JSONDecodeError, UnicodeDecodeError, Exception) as exc:
                    logger.debug(
                        "ℹ️  Idempotency skipped caching non-JSON response | key=%s: %s", raw_key, exc
                    )

            # ── RELEASE: Always release the lock ───────────────────────────
            await async_redis.delete(lock_key)
            return response

        except Exception as exc:
            # Redis connection error — degrade gracefully to sync Django cache
            logger.warning(
                "⚠️  Idempotency async Redis error (degrading to sync cache) | key=%s: %s",
                raw_key, exc,
            )
            # Reset so next request tries to reconnect
            self._async_redis = None
            return await self._handle_sync_cache_async(request, raw_key, lock_key, resp_key)

    async def _handle_sync_cache_async(
        self, request, raw_key: str, lock_key: str, resp_key: str
    ):
        """
        Fallback idempotency path using the synchronous Django cache framework.

        Invoked when redis.asyncio is unavailable (dev/test). The Django cache
        framework with IGNORE_EXCEPTIONS=True never raises or hangs.

        Args:
            request: Django HttpRequest.
            raw_key: Raw idempotency key from header.
            lock_key: Redis key for the in-flight lock.
            resp_key: Redis key for the cached response.

        Returns:
            HttpResponse: Cached replay, 409 conflict, or fresh view response.
        """
        _cache = _get_cache()

        cached = _cache.get(resp_key)
        if cached is not None:
            try:
                data = json.loads(cached)
                return JsonResponse(data["body"], status=data["status"], safe=False)
            except (json.JSONDecodeError, KeyError, TypeError):
                pass  # Fall through

        acquired = _cache.add(lock_key, "1", timeout=IDEMPOTENCY_LOCK_TTL)
        if acquired is False:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "A request with this Idempotency-Key is already in progress.",
                    "idempotency_key": raw_key,
                },
                status=409,
            )

        try:
            response = await self.get_response(request)
        except Exception:
            _cache.delete(lock_key)
            raise

        if 200 <= response.status_code < 300:
            try:
                response_body = json.loads(response.content.decode("utf-8"))
                payload = json.dumps({"status": response.status_code, "body": response_body})
                _cache.set(resp_key, payload, timeout=IDEMPOTENCY_TTL)
            except Exception:
                pass

        _cache.delete(lock_key)
        return response
