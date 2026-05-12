"""
FASHIONISTAR — Enterprise Auth Stress Tests
============================================
Tests critical concurrency guarantees of the authentication system:

  1. OTP TOCTOU Race Condition — Exactly-once OTP consumption under 500 threads
  2. Transaction Atomic Rollback — User not created if OTP generation fails
  3. Duplicate Registration Idempotency — Second register → 400, not 500
  4. ME Endpoint — Authenticated profile retrieval
  5. Health Endpoint — Kubernetes readiness probe

Requirements:
    uv run pytest apps/authentication/tests/test_stress.py -v -s

Stress test target:
    500 concurrent threads → single OTP → exactly 1 success guaranteed
"""

import threading
import pytest
from django.test import TestCase, Client
from django.urls import reverse
from unittest.mock import patch

from apps.authentication.models import UnifiedUser
from apps.authentication.services.otp import OTPService


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def create_unverified_user(email: str = None, phone: str = None) -> UnifiedUser:
    """Helper: creates a user suitable for OTP verification testing."""
    kwargs = {
        "password": "StressTest123!",
        "is_active": False,
        "is_verified": False,
        "role": "client",
        "first_name": "Stress",
        "last_name": "Test",
    }
    if email:
        kwargs["email"] = email
    if phone:
        kwargs["phone"] = phone
    return UnifiedUser.objects.create_user(**kwargs)


# ═════════════════════════════════════════════════════════════════════════════
# 1. OTP RACE CONDITION — EXACTLY ONCE SEMANTICS
# ═════════════════════════════════════════════════════════════════════════════

class TestOTPRaceCondition(TestCase):
    """
    Validates that OTP verification is idempotent under extreme concurrency.

    CRITICAL PRODUCTION REQUIREMENT:
        Under 100k RPS, multiple servers will receive identical OTP codes
        simultaneously. Exactly ONE request must succeed; all others must fail.

    TEST APPROACH:
        Spawn N threads simultaneously. Each thread calls verify_by_otp_sync()
        with the same OTP code. Only ONE should return a non-None result.

    PASS CRITERIA:
        len([r for r in results if r is not None]) == 1

    FIXED BY:
        WATCH/MULTI/EXEC optimistic locking in OTPService.verify_by_otp_sync()
        (replaced the GET+pipeline.DEL TOCTOU-vulnerable pattern)
    """

    def setUp(self):
        self.user = create_unverified_user(email=f"race.test.{id(self)}@fashionistar.io")

    def _run_thread(self, otp: str, purpose: str, results: list, lock: threading.Lock):
        """Target function for concurrent threads."""
        result = OTPService.verify_by_otp_sync(otp, purpose=purpose)
        with lock:
            results.append(result)

    def test_100_concurrent_threads_exactly_one_success(self):
        """100 concurrent OTP verification attempts — exactly 1 must succeed."""
        otp = OTPService.generate_otp_sync(self.user.id, purpose='verify')
        self.assertIsNotNone(otp, "OTP generation failed — Redis may be unavailable")

        results = []
        lock = threading.Lock()
        thread_count = 100

        threads = [
            threading.Thread(
                target=self._run_thread,
                args=(otp, 'verify', results, lock),
                daemon=True,
            )
            for _ in range(thread_count)
        ]

        # Fire all threads simultaneously via barrier synchronisation
        barrier = threading.Barrier(thread_count)
        original_target = threads[0]._target  # noqa

        def synchronized_target(otp, purpose, results, lock):
            barrier.wait()  # All threads start at the same instant
            self._run_thread(otp, purpose, results, lock)

        threads = [
            threading.Thread(
                target=synchronized_target,
                args=(otp, 'verify', results, lock),
                daemon=True,
            )
            for _ in range(thread_count)
        ]

        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        successes = [r for r in results if r is not None]
        failures  = [r for r in results if r is None]

        self.assertEqual(
            len(results), thread_count,
            f"Not all threads completed: {len(results)}/{thread_count}"
        )
        self.assertEqual(
            len(successes), 1,
            f"CRITICAL RACE CONDITION: {len(successes)} threads consumed the same OTP! "
            f"Expected exactly 1. WATCH/MULTI/EXEC fix may not be applied."
        )
        self.assertEqual(
            len(failures), thread_count - 1,
            f"Expected {thread_count - 1} failures, got {len(failures)}"
        )

        # Verify the successful result has the right user_id
        success = successes[0]
        self.assertEqual(success['user_id'], str(self.user.id))
        self.assertEqual(success['purpose'], 'verify')

    def test_500_concurrent_threads_exactly_one_success(self):
        """500 concurrent OTP verification attempts — exactly 1 must succeed."""
        otp = OTPService.generate_otp_sync(self.user.id, purpose='verify')
        self.assertIsNotNone(otp, "OTP generation failed — Redis may be unavailable")

        results = []
        lock = threading.Lock()
        thread_count = 500
        barrier = threading.Barrier(thread_count)

        def target():
            barrier.wait()
            self._run_thread(otp, 'verify', results, lock)

        threads = [threading.Thread(target=target, daemon=True) for _ in range(thread_count)]
        for t in threads: t.start()
        for t in threads: t.join(timeout=60)

        successes = [r for r in results if r is not None]
        self.assertEqual(
            len(successes), 1,
            f"CRITICAL: {len(successes)} threads consumed same OTP! "
            f"Exactly-once guarantee BROKEN under 500-thread load."
        )

    def test_otp_cannot_be_reused(self):
        """After successful verification, the same OTP code must fail."""
        otp = OTPService.generate_otp_sync(self.user.id, purpose='verify')

        # First verification — must succeed
        result1 = OTPService.verify_by_otp_sync(otp, purpose='verify')
        self.assertIsNotNone(result1, "First OTP verification failed unexpectedly")

        # Second verification with SAME code — must fail
        result2 = OTPService.verify_by_otp_sync(otp, purpose='verify')
        self.assertIsNone(
            result2,
            "REPLAY ATTACK POSSIBLE: OTP was accepted a second time after first consumption!"
        )

    def test_wrong_purpose_rejected(self):
        """OTP generated for 'verify' must not work for 'reset'."""
        otp = OTPService.generate_otp_sync(self.user.id, purpose='verify')

        result = OTPService.verify_by_otp_sync(otp, purpose='reset')
        self.assertIsNone(
            result,
            "PURPOSE BYPASS: OTP for 'verify' was accepted for 'reset' purpose!"
        )


# ═════════════════════════════════════════════════════════════════════════════
# 2. TRANSACTION ATOMIC — ROLLBACK INTEGRITY
# ═════════════════════════════════════════════════════════════════════════════

class TestAtomicTransactionIntegrity(TestCase):
    """
    Verifies that database transaction rollbacks are working correctly.

    FAIL SCENARIO (before fix):
        If Redis is down during registration, the UnifiedUser row would already
        be committed before OTP generation fails — leaving a zombie user in the
        DB that can never be verified.

    PASS CRITERIA (after fix):
        UnifiedUser must NOT exist after a failed registration.
    """

    def test_user_not_saved_when_otp_generation_fails(self):
        """
        If OTPService.generate_otp_sync() raises, registration MUST roll back.
        The user row MUST NOT exist in the database afterward.
        """
        from apps.authentication.services.registration import RegistrationService

        email = f"atomic.otp.fail.{id(self)}@fashionistar.io"

        with patch.object(
            OTPService,
            'generate_otp_sync',
            side_effect=Exception("Simulated Redis failure during OTP generation")
        ):
            with self.assertRaises(Exception, msg="RegistrationService should re-raise exceptions"):
                RegistrationService.register_sync(
                    email=email,
                    password="AtomicTest123!",
                    first_name="Atomic",
                    last_name="Test",
                    role="client",
                )

        # CRITICAL CHECK: User MUST NOT be persisted
        user_exists = UnifiedUser.objects.filter(email=email).exists()
        self.assertFalse(
            user_exists,
            "ATOMIC ROLLBACK BROKEN: User was committed to DB despite OTP generation failure! "
            "Check that transaction.atomic() wraps both create_user() AND generate_otp_sync()."
        )

    def test_user_not_saved_when_user_creation_raises_validation(self):
        """If create_user() itself raises ValidationError, no user is committed."""
        from apps.authentication.services.registration import RegistrationService

        # First registration succeeds
        email = f"dup.atomic.{id(self)}@fashionistar.io"
        RegistrationService.register_sync(
            email=email,
            password="FirstReg123!",
            first_name="First",
            last_name="User",
            role="client",
        )

        initial_count = UnifiedUser.objects.count()

        # Second registration with SAME email should raise ValidationError
        # and NOT create a second user
        from rest_framework import serializers as drf_serializers
        with self.assertRaises(drf_serializers.ValidationError):
            RegistrationService.register_sync(
                email=email,
                password="SecondReg123!",
                first_name="Second",
                last_name="User",
                role="client",
            )

        final_count = UnifiedUser.objects.count()
        self.assertEqual(
            initial_count, final_count,
            "Duplicate registration created a second user! IntegrityError not raised as ValidationError."
        )


# ═════════════════════════════════════════════════════════════════════════════
# 3. HEALTH ENDPOINT
# ═════════════════════════════════════════════════════════════════════════════

class TestHealthEndpoint(TestCase):
    """
    Verifies /health/ returns 200 with correct JSON.
    Critical for Kubernetes readiness probes — if this fails, pods are marked unhealthy.
    """

    def test_health_returns_200(self):
        """GET /health/ must return 200 with status=ok."""
        client = Client()
        response = client.get('/health/')

        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('service'), 'fashionistar-api')
        self.assertIn('database', data)

    def test_health_does_not_require_auth(self):
        """Health endpoint must be publicly accessible (no auth token needed)."""
        client = Client()
        response = client.get('/health/')
        # Should NOT redirect to login or return 401/403
        self.assertNotIn(response.status_code, [401, 403, 302])


# ═════════════════════════════════════════════════════════════════════════════
# 4. ME ENDPOINT
# ═════════════════════════════════════════════════════════════════════════════

class TestMeEndpoint(TestCase):
    """
    Verifies GET /api/v1/auth/me/ returns authenticated user profile.
    Critical for frontend Zustand rehydration on page refresh.
    """

    def setUp(self):
        from rest_framework_simplejwt.tokens import RefreshToken
        self.user = UnifiedUser.objects.create_user(
            email=f"me.test.{id(self)}@fashionistar.io",
            password="MeTest123!",
            first_name="Profile",
            last_name="User",
            is_active=True,
            is_verified=True,
        )
        refresh = RefreshToken.for_user(self.user)
        self.access_token = str(refresh.access_token)

    def test_me_returns_profile_with_valid_token(self):
        """GET /api/v1/auth/me/ with valid Bearer token → 200 with user data."""
        client = Client()
        response = client.get(
            '/api/v1/auth/me/',
            HTTP_AUTHORIZATION=f'Bearer {self.access_token}',
        )
        self.assertEqual(response.status_code, 200)
        data = response.json()

        # Handle Fashionistar envelope wrapper
        if 'data' in data:
            data = data['data']

        self.assertEqual(data.get('email'), self.user.email)
        self.assertEqual(data.get('first_name'), 'Profile')
        self.assertEqual(data.get('last_name'), 'User')
        self.assertIn('role', data)
        self.assertIn('is_verified', data)

    def test_me_returns_401_without_token(self):
        """GET /api/v1/auth/me/ without token → 401 Unauthorized."""
        client = Client()
        response = client.get('/api/v1/auth/me/')
        self.assertEqual(response.status_code, 401)

    def test_me_returns_401_with_invalid_token(self):
        """GET /api/v1/auth/me/ with invalid token → 401 Unauthorized."""
        client = Client()
        response = client.get(
            '/api/v1/auth/me/',
            HTTP_AUTHORIZATION='Bearer this.is.invalid',
        )
        self.assertEqual(response.status_code, 401)


# ═════════════════════════════════════════════════════════════════════════════
# 5. REGISTRATION IDEMPOTENCY
# ═════════════════════════════════════════════════════════════════════════════

class TestRegistrationIdempotency(TestCase):
    """
    Verifies that duplicate registrations return 400 (not 500).
    Critical for production — 500s on duplicate email could mask real DB issues.
    """

    def test_duplicate_email_returns_400(self):
        """Second registration with same email → 400 with error message."""
        client = Client()
        payload = {
            "email": f"dupe.{id(self)}@fashionistar.io",
            "password": "Duplicate123!",
            "password2": "Duplicate123!",
            "password_confirm": "Duplicate123!",
            "first_name": "Dupe",
            "last_name": "Test",
            "role": "client",
        }
        import json

        r1 = client.post(
            '/api/v1/auth/register/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(r1.status_code, 201, f"First registration failed: {r1.content}")

        r2 = client.post(
            '/api/v1/auth/register/',
            data=json.dumps(payload),
            content_type='application/json',
        )
        self.assertEqual(
            r2.status_code, 400,
            f"Duplicate registration should return 400, got {r2.status_code}: {r2.content}"
        )

        # Should not be 500
        self.assertNotEqual(
            r2.status_code, 500,
            "CRITICAL: Duplicate registration returned 500 — IntegrityError not caught!"
        )
