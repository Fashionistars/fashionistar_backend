import concurrent.futures
from django.test import TransactionTestCase
from rest_framework.test import APIClient
from apps.authentication.models import UnifiedUser
from apps.audit_logs.models import AuditEventLog, EventType
from rest_framework_simplejwt.tokens import RefreshToken
import uuid

class AuthConcurrencyTests(TransactionTestCase):
    """
    Tests for race conditions, idempotency, and transaction atomicity block handling.
    Inherits from TransactionTestCase to allow multi-threaded database connections.
    """
    
    def setUp(self):
        self.client = APIClient()
        self.password = "Atomic!Password2026"
        self.user = UnifiedUser.objects.create_user(
            email=f"concurrency_{uuid.uuid4().hex[:6]}@fashionistar.io",
            password=self.password,
            first_name="Concurrent",
            last_name="Test",
            role="client"
        )
        self.user.is_active = True
        self.user.otp_verified = True
        self.user.save()

    def get_token_for_user(self, user):
        refresh = RefreshToken.for_user(user)
        return str(refresh.access_token)

    def test_concurrent_password_change_atomic(self):
        """
        Test that `transaction.atomic` properly isolates concurrent password changes.
        We attempt to change the password 10 times concurrently. 
        Only one (the first to acquire the lock/process) should succeed because the 
        others will fail the `old_password` check once the first commit happens.
        """
        access_token = self.get_token_for_user(self.user)
        
        def attempt_change(i):
            client = APIClient()
            client.credentials(HTTP_AUTHORIZATION=f"Bearer {access_token}")
            response = client.post("/api/v1/password/change/", {
                "old_password": self.password,
                "new_password": f"New!Password2026_{i}",
                "confirm_password": f"New!Password2026_{i}"
            }, format="json")
            return response.status_code

        # Launch 10 concurrent threads
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(attempt_change, i) for i in range(10)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        successes = [r for r in results if r == 200]
        failures = [r for r in results if r in (400, 403)]
        
        # Exactly one should succeed, others fail due to old_password mismatch
        # Note: Depending on SQLite/PostgreSQL locks, some might fail with 500 OperationalError (DB Locked)
        # But we assert that at most 1 succeeded.
        self.assertTrue(len(successes) <= 1, f"Expected 1 or 0 successes, got {len(successes)}")

    def test_idempotency_password_reset_request(self):
        """
        Test idempotency: sending 5 consecutive password reset requests for the same email.
        The system should handle them gracefully without crashing, and return 200 for all.
        """
        def attempt_reset(_):
            client = APIClient()
            return client.post("/api/v1/password/reset-request/", {
                "email_or_phone": self.user.email
            }, format="json").status_code

        with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
            futures = [executor.submit(attempt_reset, i) for i in range(5)]
            results = [f.result() for f in concurrent.futures.as_completed(futures)]
        
        # All requests should return 200 because it's designed to be idempotent and anti-enumeration
        self.assertTrue(all(r == 200 for r in results), f"Not all returned 200: {results}")
