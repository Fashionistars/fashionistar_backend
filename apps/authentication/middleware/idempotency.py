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
    "/api/v1/auth/login/",
    "/api/v1/auth/logout/",
    "/api/v1/auth/token/refresh/",
    "/health/",
])


import hashlib
import json
from typing import Any, Optional
from django.core.cache import cache
from django.db import models


class IdempotencyKey:
    """
    Idempotency key manager for preventing duplicate operations
    """
    
    def __init__(self, prefix: str = 'idempotent'):
        self.prefix = prefix
    
    def generate_key(self, *args, **kwargs) -> str:
        """
        Generate an idempotency key from arguments
        
        Args:
            *args: Positional arguments to include in key
            **kwargs: Keyword arguments to include in key
            
        Returns:
            Idempotency key string
        """
        # Combine all arguments
        data = {
            'args': args,
            'kwargs': kwargs
        }
        
        # Convert to stable JSON string
        json_str = json.dumps(data, sort_keys=True)
        
        # Generate hash
        hash_value = hashlib.sha256(json_str.encode()).hexdigest()
        
        return f"{self.prefix}:{hash_value}"
    
    def check_and_set(
        self, 
        key: str, 
        value: Any = True, 
        ttl: int = 3600
    ) -> bool:
        """
        Check if key exists and set if not (atomic operation)
        
        Args:
            key: Idempotency key
            value: Value to store
            ttl: Time to live in seconds
            
        Returns:
            True if key was set (operation should proceed)
            False if key existed (operation already performed)
        """
        # Try to add key (will fail if exists)
        return cache.add(key, value, ttl)
    
    def get(self, key: str) -> Optional[Any]:
        """Get value for idempotency key"""
        return cache.get(key)
    
    def delete(self, key: str) -> None:
        """Delete idempotency key"""
        cache.delete(key)


class IdempotentOperation(models.Model):
    """
    Database-backed idempotent operations for critical operations
    """
    key = models.CharField(max_length=255, unique=True, db_index=True)
    operation = models.CharField(max_length=100)
    result = models.JSONField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    
    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=['key', 'operation']),
            models.Index(fields=['created_at']),
        ]




class IdempotencyMiddleware:
    """
    Dual-mode ASGI + WSGI middleware for POST endpoint idempotency.

    Position in MIDDLEWARE list:
        Place AFTER SecurityAuditMiddleware but BEFORE CorsMiddleware
        so that replayed responses still get proper CORS headers.
    """

    async_capable = True
    sync_capable = True

    def __init__(self, get_response):
        self.get_response = get_response
        from asgiref.sync import iscoroutinefunction, markcoroutinefunction
        if iscoroutinefunction(self.get_response):
            markcoroutinefunction(self)

    def __call__(self, request):
        """Synchronous path — WSGI (manage.py runserver / gunicorn)."""
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
        # If Redis is unreachable or throws a connection error, acquired is None
        # (due to IGNORE_EXCEPTIONS = True). We gracefully degrade and allow the
        # request to proceed as if lock was acquired. Only block on explicit False.
        if acquired is False:
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

    async def __acall__(self, request):
        """Asynchronous path — ASGI (Uvicorn / Daphne). Zero thread-overhead."""
        # ── Only intercept POST requests ───────────────────────────────────
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
        _cache = _get_cache()  # Resolve once per request

        # ── CHECK: Cached response exists? ────────────────────────────────
        cached = await _cache.aget(resp_key)
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

        # ── LOCK: Prevent concurrent in-flight requests with same key ──────
        acquired = await _cache.aadd(lock_key, "1", timeout=IDEMPOTENCY_LOCK_TTL)
        if acquired is False:
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
            response = await self.get_response(request)
        except Exception:
            # Always release the lock on exception — never leave it dangling
            await _cache.adelete(lock_key)
            raise

        # ── CACHE: Store successful responses only (2xx status codes) ──────
        if 200 <= response.status_code < 300:
            try:
                response_body = json.loads(response.content.decode("utf-8"))
                payload = json.dumps({
                    "status": response.status_code,
                    "body": response_body,
                })
                await _cache.aset(resp_key, payload, timeout=IDEMPOTENCY_TTL)
                logger.info(
                    "💾 Idempotency STORED | key=%s | status=%s | path=%s | TTL=%ss",
                    raw_key, response.status_code, request.path, IDEMPOTENCY_TTL,
                )
            except (json.JSONDecodeError, UnicodeDecodeError, Exception) as exc:
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
        await _cache.adelete(lock_key)

        return response
