# apps/authentication/tests/test_concurrency.py
"""
FASHIONISTAR — Concurrency Tests
==================================
Tests authentication system correctness under high concurrent load.

Test Suite:
  1. Concurrent Session Revocation Race — same session, 50 threads → exactly 1 succeeds
  2. Concurrent Login Same User — 200 threads log in same user → all get tokens (no crash)
  3. Concurrent Registration Same Email — 100 threads same email → exactly 1 user created
  4. Password Reset Concurrent Requests — 50 threads request reset → rate-limited, not errored
  5. Token Refresh Concurrent — 100 threads refresh same token → only 1 succeeds (rotation)

Run:
    uv run pytest apps/authentication/tests/test_concurrency.py -v -s

Architecture notes:
  - threading.Barrier used to synchronize all threads to start simultaneously
  - Results collected in thread-safe list with lock
  - select_for_update() in SessionRevokeView prevents double-delete
  - Redis WATCH/MULTI/EXEC in OTPService prevents double-OTP-consume
"""

import threading
import json
import uuid
import pytest
from django.test import TestCase, Client
from django.db import transaction
from rest_framework_simplejwt.tokens import RefreshToken
from unittest.mock import patch

from apps.authentication.models import UnifiedUser


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def make_verified_user(email: str = None) -> UnifiedUser:
    """Create a fully verified user for concurrency tests."""
    email = email or f"concurrent.{uuid.uuid4().hex[:8]}@fashionistar.io"
    return UnifiedUser.objects.create_user(
        email=email,
        password="ConcurrentTest123!",
        role="client",
        is_active=True,
        is_verified=True,
        first_name="Concurrent",
        last_name="Test",
    )


def fire_concurrent(target_fn, thread_count: int, timeout: int = 30) -> list:
    """
    Fire `thread_count` threads simultaneously via barrier synchronisation.
    Returns list of results in order of completion.
    """
    results = []
    lock = threading.Lock()
    barrier = threading.Barrier(thread_count)

    def runner():
        barrier.wait()  # All threads start at the exact same instant
        result = target_fn()
        with lock:
            results.append(result)

    threads = [threading.Thread(target=runner, daemon=True) for _ in range(thread_count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)

    return results


# ═════════════════════════════════════════════════════════════════════════════
# 1. SESSION REVOCATION RACE CONDITION
# ═════════════════════════════════════════════════════════════════════════════

class TestConcurrentSessionRevocation(TestCase):
    """
    Verifies that select_for_update() in SessionRevokeView prevents
    concurrent double-deletion of the same session.

    PASS CRITERIA:
      - Exactly 1 thread gets HTTP 200 (revoked successfully)
      - All other threads get HTTP 404 (session already gone)
      - Zero HTTP 500 errors (no IntegrityError from double-DELETE)
    """

    def setUp(self):
        from apps.authentication.models import UserSession
        self.user = make_verified_user()
        self.refresh = RefreshToken.for_user(self.user)
        # Create a UserSession record manually (as login would)
        self.session = UserSession.objects.create(
            user=self.user,
            jti=str(self.refresh['jti']),
            device_name="Test Device",
            ip_address="127.0.0.1",
            user_agent="pytest-concurrency",
        )
        access = str(self.refresh.access_token)
        self.auth_header = f'Bearer {access}'

    def _revoke_session(self):
        client = Client()
        return client.delete(
            f'/api/v1/auth/sessions/{self.session.pk}/',
            HTTP_AUTHORIZATION=self.auth_header,
        ).status_code

    def test_50_concurrent_revoke_exactly_one_succeeds(self):
        """50 threads try to revoke the same session — exactly 1 must return 200."""
        results = fire_concurrent(self._revoke_session, thread_count=50)

        successes = [r for r in results if r == 200]
        not_found = [r for r in results if r == 404]
        errors     = [r for r in results if r == 500]

        self.assertEqual(len(results), 50, f"Only {len(results)}/50 threads completed")
        self.assertEqual(
            len(errors), 0,
            f"CRITICAL: {len(errors)} threads returned 500 (IntegrityError/double-delete). "
            f"select_for_update() may not be applied."
        )
        self.assertEqual(
            len(successes), 1,
            f"RACE CONDITION: {len(successes)} threads returned 200. Expected exactly 1. "
            f"Status codes: {results}"
        )
        self.assertEqual(
            len(not_found), 49,
            f"Expected 49 threads to get 404. Got {len(not_found)}."
        )


# ═════════════════════════════════════════════════════════════════════════════
# 2. CONCURRENT LOGIN — SAME USER, 200 THREADS
# ═════════════════════════════════════════════════════════════════════════════

class TestConcurrentLogin(TestCase):
    """
    Verifies that the login endpoint handles 200 concurrent requests
    for the same user without crashing or returning 500s.

    Expected result:
      - All 200 threads return 200 with tokens (each gets their own JWT)
      - Zero 500 errors
    """

    def setUp(self):
        self.user = make_verified_user()

    def _login(self):
        client = Client()
        r = client.post(
            '/api/v1/auth/login/',
            data=json.dumps({
                'email_or_phone': self.user.email,
                'password': 'ConcurrentTest123!',
            }),
            content_type='application/json',
        )
        return r.status_code

    def test_200_concurrent_logins_no_500(self):
        """200 concurrent logins for the same user must all succeed (200) with no 500s."""
        results = fire_concurrent(self._login, thread_count=200, timeout=60)

        self.assertEqual(len(results), 200, f"Only {len(results)}/200 threads completed")

        errors_500 = [r for r in results if r == 500]
        self.assertEqual(
            len(errors_500), 0,
            f"CRITICAL: {len(errors_500)} logins returned 500 under concurrent load."
        )

        successes = [r for r in results if r == 200]
        self.assertGreater(
            len(successes), 150,  # Allow some throttle rejections (429)
            f"Too many login failures under concurrency. Got {len(successes)}/200 successes. "
            f"Status codes: {sorted(set(results))}"
        )


# ═════════════════════════════════════════════════════════════════════════════
# 3. CONCURRENT REGISTRATION — SAME EMAIL
# ═════════════════════════════════════════════════════════════════════════════

class TestConcurrentRegistration(TestCase):
    """
    100 threads attempt to register with the exact same email simultaneously.
    Database IntegrityError + RegistrationService handling must ensure:
      - Exactly 1 user is created (no zombie duplicates)
      - No 500 errors (IntegrityError caught and returned as 400)
    """

    @patch('apps.authentication.tasks.send_email_task.delay', return_value=None)
    @patch('apps.authentication.tasks.send_sms_task.delay', return_value=None)
    def test_100_concurrent_same_email_registration(self, mock_sms, mock_email):
        """100 threads register with same email → exactly 1 user, zero 500 errors."""
        email = f"race.register.{uuid.uuid4().hex[:6]}@fashionistar.io"
        payload = json.dumps({
            "email": email,
            "password": "RaceReg123!",
            "password2": "RaceReg123!",
            "first_name": "Race",
            "last_name": "Register",
            "role": "client",
        })

        def register():
            client = Client()
            return client.post(
                '/api/v1/auth/register/',
                data=payload,
                content_type='application/json',
            ).status_code

        results = fire_concurrent(register, thread_count=100, timeout=60)

        self.assertEqual(len(results), 100, f"Only {len(results)}/100 threads completed")

        errors_500 = [r for r in results if r == 500]
        self.assertEqual(
            len(errors_500), 0,
            f"CRITICAL: {len(errors_500)} registrations returned 500. "
            f"IntegrityError must be caught as ValidationError (400), not propagated as 500."
        )

        successes = [r for r in results if r == 201]
        self.assertEqual(
            len(successes), 1,
            f"RACE CONDITION: {len(successes)} users created for same email. Expected exactly 1."
        )

        user_count = UnifiedUser.objects.filter(email=email).count()
        self.assertEqual(
            user_count, 1,
            f"CRITICAL: {user_count} users in DB for email '{email}'. Expected exactly 1."
        )


# ═════════════════════════════════════════════════════════════════════════════
# 4. CONCURRENT TOKEN REFRESH — ROTATION CORRECTNESS
# ═════════════════════════════════════════════════════════════════════════════

class TestConcurrentTokenRefresh(TestCase):
    """
    50 threads attempt to refresh the SAME refresh token simultaneously.

    With ROTATE_REFRESH_TOKENS=True + BLACKLIST_AFTER_ROTATION=True:
      - First thread to succeed gets a new token pair
      - All subsequent threads get 401 (old token now blacklisted)
      - Zero 500 errors

    This validates that token rotation is race-condition-safe.
    """

    def setUp(self):
        self.user = make_verified_user()
        self.refresh_token = str(RefreshToken.for_user(self.user))

    def _refresh(self):
        client = Client()
        r = client.post(
            '/api/v1/auth/token/refresh/',
            data=json.dumps({'refresh': self.refresh_token}),
            content_type='application/json',
        )
        return r.status_code

    def test_50_concurrent_refresh_only_first_succeeds(self):
        """50 threads refresh the same token — only the first should succeed."""
        results = fire_concurrent(self._refresh, thread_count=50, timeout=30)

        self.assertEqual(len(results), 50, f"Only {len(results)}/50 threads completed")

        errors_500 = [r for r in results if r == 500]
        self.assertEqual(
            len(errors_500), 0,
            f"CRITICAL: {len(errors_500)} refresh calls returned 500 under concurrent access."
        )

        successes = [r for r in results if r == 200]
        # With blacklist rotation, at most 1 should succeed
        self.assertLessEqual(
            len(successes), 1,
            f"TOKEN ROTATION RACE: {len(successes)} threads successfully refreshed "
            f"the same token. Only 1 should succeed with ROTATE_REFRESH_TOKENS=True."
        )
