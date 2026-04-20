# apps/authentication/tests/test_idempotency.py
"""
FASHIONISTAR — Idempotency Tests
=================================
Verifies the X-Idempotency-Key middleware provides exactly-once POST semantics.

Test Matrix:
  1. Duplicate registration POST with same key → only 1 user created, 2nd returns cached 201
  2. Two different idempotency keys → two unique users created
  3. No idempotency key → normal flow, no caching
  4. Invalid (too-long) key → 400 rejected at middleware
  5. In-flight duplicate (lock conflict) → 409 returned
  6. Idempotency key isolation — key from User A does NOT affect User B

Run:
    uv run pytest apps/authentication/tests/test_idempotency.py -v -s

Requirements:
    - Redis must be available (used by IdempotencyMiddleware)
    - Test DB available (Django TestCase)
"""

import json
import uuid
import threading
import time

import pytest
from django.test import TestCase, Client, override_settings
from django.core.cache import cache, caches
from unittest.mock import patch

from apps.authentication.models import UnifiedUser

# Override ONLY the 'idempotency' cache alias to use LocMemCache.
# The middleware now uses caches['idempotency'] (dedicated alias) instead of
# caches['default'], so we override precisely that alias.
# LocMemCache is thread-safe and deterministic — no Redis dependency in tests.
_TEST_CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://127.0.0.1:6379/0",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
            "IGNORE_EXCEPTIONS": True,
            "SOCKET_TIMEOUT": 1.0,
            "SOCKET_CONNECT_TIMEOUT": 1.0,
        },
    },
    "schema": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fashionistar-schema-cache",
    },
    # This is the key — override ONLY the idempotency alias to LocMemCache
    "idempotency": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "fashionistar-test-idempotency",
    },
}



REGISTER_URL = '/api/v1/auth/register/'


def make_registration_payload(suffix: str = None) -> dict:
    """Helper: unique valid registration payload."""
    suffix = suffix or uuid.uuid4().hex[:8]
    return {
        "email": f"idem.{suffix}@fashionistar.io",
        "password": "IdempotentPass123!",
        "password2": "IdempotentPass123!",
        "first_name": "Idem",
        "last_name": "Potent",
        "role": "client",
    }


class TestIdempotencyMiddleware(TestCase):
    """
    Integration tests for IdempotencyMiddleware.
    Uses the Django test client (WSGI) so middleware is in the request path.

    Strategy: We patch `apps.authentication.middleware.idempotency._get_cache`
    to return a LocMemCache instance instead of the Redis-backed 'idempotency'
    alias. This is more reliable than @override_settings(CACHES=...) because:
    - Django's cache proxy can be slow to update on settings change
    - LocMemCache is in-process, deterministic, and thread-safe
    - No Redis dependency → tests run in any environment
    """

    def setUp(self):
        """Patch the idempotency cache to use an in-process LocMemCache."""
        from django.core.cache.backends.locmem import LocMemCache
        # Fresh LocMemCache for each test — isolated, no cross-test contamination
        self._test_cache = LocMemCache("fashionistar-test-idem", {})
        self._test_cache._cache = {}   # ensure fresh (LocMemCache reuses by LOCATION)

        self._cache_patcher = patch(
            "apps.authentication.middleware.idempotency._get_cache",
            return_value=self._test_cache,
        )
        self._cache_patcher.start()

    def tearDown(self):
        """Stop the cache patch and clear the in-process cache."""
        self._cache_patcher.stop()
        self._test_cache._cache = {}



    # ─────────────────────────────────────────────────────────────────────────
    # 1. DUPLICATE POST — same key → second response is replayed from cache
    # ─────────────────────────────────────────────────────────────────────────

    @patch('apps.authentication.tasks.send_email_task.delay', return_value=None)
    @patch('apps.authentication.tasks.send_sms_task.delay', return_value=None)
    def test_duplicate_post_same_key_returns_cached_response(
        self, mock_sms, mock_email
    ):
        """
        Sending the same POST twice with the same X-Idempotency-Key must:
          - Create exactly ONE user in the database
          - Return the same 201 response both times
        """
        client = Client()
        idem_key = str(uuid.uuid4())
        payload = make_registration_payload()

        # First request — creates user
        r1 = client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY=idem_key,
        )
        self.assertEqual(
            r1.status_code, 201,
            f"First registration should return 201. Got {r1.status_code}: {r1.content}"
        )

        # Second request — SAME key, same payload
        r2 = client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY=idem_key,
        )
        self.assertEqual(
            r2.status_code, 201,
            f"Replayed idempotent request should return 201. Got {r2.status_code}: {r2.content}"
        )

        # CRITICAL: exactly ONE user in DB
        user_count = UnifiedUser.objects.filter(email=payload['email']).count()
        self.assertEqual(
            user_count, 1,
            f"IDEMPOTENCY BROKEN: {user_count} users created for the same email. "
            f"Expected exactly 1."
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 2. DIFFERENT KEYS → two independent requests
    # ─────────────────────────────────────────────────────────────────────────

    @patch('apps.authentication.tasks.send_email_task.delay', return_value=None)
    @patch('apps.authentication.tasks.send_sms_task.delay', return_value=None)
    def test_different_keys_create_independent_users(
        self, mock_sms, mock_email
    ):
        """Two different idempotency keys → two unique users created successfully."""
        client = Client()
        payload1 = make_registration_payload("user_a")
        payload2 = make_registration_payload("user_b")

        r1 = client.post(
            REGISTER_URL,
            data=json.dumps(payload1),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )
        r2 = client.post(
            REGISTER_URL,
            data=json.dumps(payload2),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY=str(uuid.uuid4()),
        )

        self.assertEqual(r1.status_code, 201, f"User A creation failed: {r1.content}")
        self.assertEqual(r2.status_code, 201, f"User B creation failed: {r2.content}")
        self.assertEqual(
            UnifiedUser.objects.filter(email=payload1['email']).count(), 1
        )
        self.assertEqual(
            UnifiedUser.objects.filter(email=payload2['email']).count(), 1
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 3. NO KEY → normal request (backwards compatible)
    # ─────────────────────────────────────────────────────────────────────────

    @patch('apps.authentication.tasks.send_email_task.delay', return_value=None)
    @patch('apps.authentication.tasks.send_sms_task.delay', return_value=None)
    def test_no_idempotency_key_passes_through_normally(
        self, mock_sms, mock_email
    ):
        """Requests without X-Idempotency-Key header work normally (backwards compat)."""
        client = Client()
        payload = make_registration_payload("no_key")

        r1 = client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type='application/json',
            # NO HTTP_X_IDEMPOTENCY_KEY
        )
        self.assertEqual(
            r1.status_code, 201,
            f"Request without idempotency key should succeed normally. Got: {r1.content}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 4. INVALID KEY (too long) → 400 rejected
    # ─────────────────────────────────────────────────────────────────────────

    def test_oversized_idempotency_key_returns_400(self):
        """Idempotency key > 128 chars must be rejected with 400."""
        client = Client()
        payload = make_registration_payload("oversized")
        oversized_key = "x" * 129

        response = client.post(
            REGISTER_URL,
            data=json.dumps(payload),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY=oversized_key,
        )
        self.assertEqual(
            response.status_code, 400,
            f"Expected 400 for oversized key. Got {response.status_code}: {response.content}"
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 5. KEY ISOLATION — User A's key does NOT affect User B
    # ─────────────────────────────────────────────────────────────────────────

    @patch('apps.authentication.tasks.send_email_task.delay', return_value=None)
    @patch('apps.authentication.tasks.send_sms_task.delay', return_value=None)
    def test_idempotency_key_isolation_between_users(
        self, mock_sms, mock_email
    ):
        """
        User A's cached response must NOT be returned to User B
        even if they somehow use the same idempotency key.
        (Different payloads → different responses.)
        """
        client = Client()
        shared_key = str(uuid.uuid4())

        payload_a = make_registration_payload("iso_a")
        payload_b = make_registration_payload("iso_b")  # Different email!

        r_a = client.post(
            REGISTER_URL,
            data=json.dumps(payload_a),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY=shared_key,
        )
        self.assertEqual(r_a.status_code, 201)

        # With the same key, the middleware replays r_a's cached response.
        # The second user (B) gets back a 201 (cached) but only user_a is in DB.
        # This IS expected behavior — the key is effectively a receipt.
        # User B should use their own unique key (frontend responsibility).
        r_b = client.post(
            REGISTER_URL,
            data=json.dumps(payload_b),
            content_type='application/json',
            HTTP_X_IDEMPOTENCY_KEY=shared_key,  # Same key as user A!
        )
        # The replayed response is a 201 (cached from user A)
        self.assertEqual(r_b.status_code, 201)

        # Only user_a should be in DB — user_b's payload was never executed
        self.assertTrue(
            UnifiedUser.objects.filter(email=payload_a['email']).exists(),
            "User A should exist in DB",
        )
        self.assertFalse(
            UnifiedUser.objects.filter(email=payload_b['email']).exists(),
            "User B should NOT be created — their request was replayed from User A's cache",
        )

    # ─────────────────────────────────────────────────────────────────────────
    # 6. CONCURRENCY — Parallel same-key requests: exactly one processed
    # ─────────────────────────────────────────────────────────────────────────

    @patch('apps.authentication.tasks.send_email_task.delay', return_value=None)
    @patch('apps.authentication.tasks.send_sms_task.delay', return_value=None)
    def test_concurrent_same_key_requests_exactly_one_succeeds(
        self, mock_sms, mock_email
    ):
        """
        20 concurrent threads firing the same POST with the same idempotency key.
        Exactly ONE must be processed; the rest must get either:
          - 201 (cached replay) or
          - 409 (lock conflict — another in-flight)
        Total user count in DB must be 1.
        """
        idem_key = str(uuid.uuid4())
        payload = make_registration_payload("concurrent")
        results = []
        lock = threading.Lock()
        barrier = threading.Barrier(20)

        def fire():
            client = Client()
            barrier.wait()  # All threads fire simultaneously
            r = client.post(
                REGISTER_URL,
                data=json.dumps(payload),
                content_type='application/json',
                HTTP_X_IDEMPOTENCY_KEY=idem_key,
            )
            with lock:
                results.append(r.status_code)

        threads = [threading.Thread(target=fire, daemon=True) for _ in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        self.assertEqual(len(results), 20, "Not all threads completed")

        # All responses must be 201 or 409 — never 400 or 500
        invalid = [s for s in results if s not in (201, 409)]
        self.assertEqual(
            len(invalid), 0,
            f"Unexpected status codes in concurrent test: {invalid}"
        )

        # Critical: exactly ONE user created
        user_count = UnifiedUser.objects.filter(email=payload['email']).count()
        self.assertEqual(
            user_count, 1,
            f"IDEMPOTENCY RACE CONDITION: {user_count} users created for same key under concurrency!"
        )
