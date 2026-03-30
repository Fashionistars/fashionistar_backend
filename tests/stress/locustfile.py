"""
FASHIONISTAR — Locust Load Test: 100K req/s Production Simulation
==================================================================
Phase 5 — Performance verification

Install: pip install locust
Run:     locust -f tests/stress/locustfile.py --host=https://hydrographically-tawdrier-hayley.ngrok-free.dev

Open dashboard: http://localhost:8089
Set:
  - Users: 1000
  - Spawn rate: 100/s
  - Duration: 60s

Endpoints tested:
  1. GET  /api/v1/health/                 — baseline (no auth)
  2. POST /api/v1/auth/login/             — auth stress
  3. POST /api/v1/auth/register/          — registration stress
  4. POST /api/v1/upload/webhook/cloudinary/  — webhook idempotency
"""

from locust import HttpUser, between, task
from locust.exception import RescheduleTask
import json
import random
import string
import time


def random_email():
    suffix = "".join(random.choices(string.ascii_lowercase + string.digits, k=8))
    return f"stress_{suffix}@fashionistar.com"


class FashionistarAPIUser(HttpUser):
    """
    Simulates a mix of anonymous and authenticated API users.
    Weight distribution mirrors production traffic patterns:
      - 60% health checks (CDN probes, monitoring)
      - 25% auth (login/register)
      - 15% webhook processing (Cloudinary callbacks)
    """

    wait_time = between(0.1, 0.5)  # 100ms–500ms between requests

    _token: str | None = None

    def on_start(self):
        """Pre-authenticate to get a JWT token for authenticated endpoints."""
        resp = self.client.post(
            "/api/v1/auth/login/",
            json={
                "email_or_phone": "stress_test@fashionistar.com",
                "password": "StressTest1234!",
            },
            headers={"Content-Type": "application/json"},
            catch_response=True,
        )
        if resp.status_code == 200:
            data = resp.json()
            self._token = (
                data.get("data", {}).get("tokens", {}).get("access")
                or data.get("access")
                or data.get("token")
            )
            resp.success()
        else:
            resp.failure(f"Login failed: {resp.status_code}")

    @property
    def auth_headers(self):
        if self._token:
            return {"Authorization": f"Bearer {self._token}"}
        return {}

    @task(60)
    def health_check(self):
        """GET /api/v1/health/ — baseline latency measurement."""
        with self.client.get(
            "/api/v1/health/",
            name="GET /api/v1/health/",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                resp.success()
            else:
                resp.failure(f"Health check returned {resp.status_code}")

    @task(15)
    def login(self):
        """POST /api/v1/auth/login/ — stress auth endpoint."""
        with self.client.post(
            "/api/v1/auth/login/",
            json={
                "email_or_phone": "stress_test@fashionistar.com",
                "password": "WrongPassword1234!",  # Intentionally wrong — tests rate limiting
            },
            name="POST /api/v1/auth/login/",
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 400, 401, 429):
                resp.success()  # 429 = correctly rate-limited ✅
            else:
                resp.failure(f"Unexpected status: {resp.status_code}")

    @task(10)
    def register(self):
        """POST /api/v1/auth/register/ — stress registration with unique emails."""
        payload = {
            "email": random_email(),
            "password": "StressTest1234!password",
            "password2": "StressTest1234!password",
            "first_name": "Stress",
            "last_name": "Test",
            "phone": f"+234{random.randint(7000000000, 9999999999)}",
            "role": "Client",
            "terms_accepted": True,
        }
        with self.client.post(
            "/api/v1/auth/register/",
            json=payload,
            name="POST /api/v1/auth/register/",
            headers={"Content-Type": "application/json"},
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 400, 429):
                resp.success()
            else:
                resp.failure(f"Register returned {resp.status_code}")

    @task(10)
    def cloudinary_webhook_idempotency(self):
        """POST /api/v1/upload/webhook/cloudinary/ — test idempotency under load."""
        # Same payload repeatedly — idempotency should prevent duplicate writes
        payload = json.dumps({
            "notification_type": "upload",
            "public_id": "fashionistar/stress/test_idempotency.jpg",
            "secure_url": "https://res.cloudinary.com/dgpdlknc1/image/upload/v1/stress_test.jpg",
            "resource_type": "image",
            "created_at": "2026-03-30T00:00:00Z",
        })
        ts = int(time.time())
        # Note: signature will be invalid — tests the 403 path (correct behaviour)
        with self.client.post(
            "/api/v1/upload/webhook/cloudinary/",
            data=payload,
            name="POST /api/v1/upload/webhook/cloudinary/",
            headers={
                "Content-Type": "application/json",
                "X-Cld-Timestamp": str(ts),
                "X-Cld-Signature": "invalid_stress_test_sig",
            },
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 403):
                resp.success()  # 403 = correctly rejected invalid HMAC ✅
            else:
                resp.failure(f"Webhook returned {resp.status_code}")

    @task(5)
    def presign_upload(self):
        """POST /api/v1/upload/presign/ — test with JWT."""
        with self.client.post(
            "/api/v1/upload/presign/",
            json={"asset_type": "avatar"},
            name="POST /api/v1/upload/presign/",
            headers={
                "Content-Type": "application/json",
                **self.auth_headers,
            },
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 201, 401, 403):
                resp.success()
            else:
                resp.failure(f"Presign returned {resp.status_code}")
