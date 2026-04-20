# apps/authentication/middleware/idempotency.py
"""
FASHIONISTAR — Idempotency Middleware
======================================
Implements the Idempotency Key pattern for all stateful POST endpoints.

Purpose:
    Under 100,000 RPS with network retries, the same registration or
    checkout POST can arrive multiple times — creating duplicate users,
    orders, or payments. This middleware guarantees exactly-once semantics.

How it works:
    1. Client sends `X-Idempotency-Key: <uuid4>` header with every POST.
    2. Middleware checks Redis for an existing cached response under that key.
       - HIT  → return the original response immediately (no view called).
       - LOCK → another request with the same key is in-flight; return 409.
       - MISS → proceed; acquire SETNX lock; call view; store response; release lock.
    3. Response is cached for IDEMPOTENCY_TTL seconds (default: 86400 = 24 hours).

Protected methods:
    POST only (idempotency is not meaningful for GET/PUT/PATCH/DELETE without
    semantic consideration — and those methods are intrinsically idempotent).

Endpoints skipped (whitelisted):
    - Token refresh  (/token/refresh/)  — by design stateless; no key needed.
    - Logout         (/logout/)         — idempotent on its own.
    - Health         (/health/)         — GET, never POST.

Redis key schema:
    idempotency:{key}:lock     → 1 (set during processing, TTL=30s)
    idempotency:{key}:response → JSON dict (set after success, TTL=24h)

Dependencies:
    - django_redis (already installed)
    - django cache 'default' backend (Redis)

Usage (frontend):
    import { v4 as uuidv4 } from 'uuid'
    const idempotencyKey = uuidv4()
    axios.post('/api/v1/auth/register/', payload, {
        headers: { 'X-Idempotency-Key': idempotencyKey }
    })

Enterprise Reference:
    - Stripe's Idempotency Keys: https://stripe.com/docs/api/idempotent_requests
    - Uber's Idempotency Framework (2020 SRECon)
"""

import json
import logging
import uuid

from django.core.cache import caches
from django.http import JsonResponse

logger = logging.getLogger("application")

# ─── Configuration ────────────────────────────────────────────────────────────

# CACHE_ALIAS — reads from the dedicated 'idempotency' backend (Redis in prod,
# LocMemCache in tests). Falls back to 'default' if not configured.
IDEMPOTENCY_CACHE_ALIAS = "idempotency"


def _get_cache():
    """
    Return the idempotency cache backend.
    Gracefully falls back to 'default' if 'idempotency' alias is not defined.
    """
    try:
        return caches[IDEMPOTENCY_CACHE_ALIAS]
    except Exception:
        return caches["default"]


IDEMPOTENCY_HEADER = "HTTP_X_IDEMPOTENCY_KEY"   # Django META key (X-Idempotency-Key)
IDEMPOTENCY_TTL = 60 * 60 * 24                    # 24 hours in seconds
IDEMPOTENCY_LOCK_TTL = 30                         # In-flight lock TTL (seconds)
IDEMPOTENCY_LOCK_PREFIX = "idempotency:lock:"
IDEMPOTENCY_RESP_PREFIX = "idempotency:resp:"

# Endpoints that deliberately skip idempotency (always fast-path through)
IDEMPOTENCY_SKIP_PATHS = frozenset([
    "/api/v1/auth/logout/",
    "/api/v1/auth/token/refresh/",
    "/health/",
])


class IdempotencyMiddleware:
    """
    WSGI-compatible Django middleware for POST endpoint idempotency.

    Position in MIDDLEWARE list:
        Place AFTER SecurityAuditMiddleware but BEFORE CorsMiddleware
        so that replayed responses still get proper CORS headers.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        # ── Only intercept POST requests ───────────────────────────────────
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
        _cache = _get_cache()  # Resolve once per request (Redis in prod, LocMemCache in tests)

        # ── CHECK: Cached response exists? ────────────────────────────────
        cached = _cache.get(resp_key)
        if cached is not None:
            logger.info(
                "♻️  Idempotency HIT | key=%s | path=%s | Replaying cached response.",
                raw_key, request.path,
            )
            try:
                data = json.loads(cached)
                return JsonResponse(data["body"], status=data["status"], safe=False)
            except (json.JSONDecodeError, KeyError, TypeError) as exc:
                logger.warning(
                    "⚠️  Idempotency cache deserialization failed | key=%s: %s",
                    raw_key, exc,
                )
                # Fall through to normal request processing (safe degradation)

        # ── LOCK: Prevent concurrent in-flight requests with same key ──────
        acquired = _cache.add(lock_key, "1", timeout=IDEMPOTENCY_LOCK_TTL)
        if not acquired:
            logger.warning(
                "⚠️  Idempotency LOCK CONFLICT | key=%s | path=%s | "
                "In-flight request detected. Returning 409.",
                raw_key, request.path,
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

        # ── PROCESS: Call the actual view ──────────────────────────────────
        try:
            response = self.get_response(request)
        except Exception:
            # Always release the lock on exception — never leave it dangling
            _cache.delete(lock_key)
            raise

        # ── CACHE: Store successful responses only (2xx status codes) ──────
        # Do NOT cache errors (4xx, 5xx) — let the client retry naturally.
        if 200 <= response.status_code < 300:
            try:
                response_body = json.loads(response.content.decode("utf-8"))
                payload = json.dumps({
                    "status": response.status_code,
                    "body": response_body,
                })
                _cache.set(resp_key, payload, timeout=IDEMPOTENCY_TTL)
                logger.info(
                    "💾 Idempotency STORED | key=%s | status=%s | path=%s | TTL=%ss",
                    raw_key, response.status_code, request.path, IDEMPOTENCY_TTL,
                )
            except (json.JSONDecodeError, UnicodeDecodeError, Exception) as exc:
                # Non-JSON response (e.g. binary) — skip caching, not an error
                logger.debug(
                    "ℹ️  Idempotency skipped caching non-JSON response | key=%s: %s",
                    raw_key, exc,
                )
        else:
            logger.debug(
                "🚫 Idempotency NOT cached (non-2xx status=%s) | key=%s | path=%s",
                response.status_code, raw_key, request.path,
            )

        # ── RELEASE: Delete in-flight lock ────────────────────────────────
        _cache.delete(lock_key)

        return response
