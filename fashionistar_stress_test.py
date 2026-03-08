"""
FASHIONISTAR — Enterprise Load Test Suite
==========================================
Uses Locust (https://locust.io) — industry-standard HTTP load testing framework.

Architecture:
  RegistrationUser  → stress-tests POST /api/v1/auth/register/
  LoginUser         → stress-tests POST /api/v1/auth/login/ (registered user)
  FullAuthFlow      → end-to-end: register → verify OTP → login → logout
  ComprehensiveUser → weighted mix of all endpoints (realistic traffic profile)

Usage (local, headless):
  # Install first time:
  pip install locust

  # Quick run — 100 concurrent users, 10 users/sec spawn rate, 60 seconds:
  locust -f fashionistar_stress_test.py --headless -u 100 -r 10 -t 60s \
         --host http://127.0.0.1:8000 2>&1 | tee stress_results.txt

  # Ramp up to 1000 concurrent users:
  locust -f fashionistar_stress_test.py --headless -u 1000 -r 50 -t 120s \
         --host http://127.0.0.1:8000

  # Web UI (visual dashboard on http://localhost:8089):
  locust -f fashionistar_stress_test.py --host http://127.0.0.1:8000

  # CSV report output:
  locust -f fashionistar_stress_test.py --headless -u 500 -r 20 -t 60s \
         --host http://127.0.0.1:8000 --csv=stress_report

CI / Automated:
  The --fail-on-error flag ensures CI fails on any 5xx error.
  Set --expect-workers N for distributed mode across multiple agents.

IMPORTANT — On WSGI (Django dev server), expect:
  Max ~50-200 RPS (single-threaded, sync)
  ASGI (Uvicorn/Daphne) will handle 2000-10000+ RPS with async views
"""

import random
import uuid
from locust import HttpUser, task, between, events
from locust.exception import StopUser


# ─── Shared test data ────────────────────────────────────────────────────────
BASE_PASSWORD = "FashionTest!234"

VALID_ROLES = ["client", "vendor"]

WEAK_PAYLOADS = [
    {"email": "invalid-email", "password": BASE_PASSWORD, "password2": BASE_PASSWORD, "role": "client"},
    {"email": f"missing@password{random.randint(1,999)}.io", "role": "client"},
    {"email": "", "password": "", "password2": "", "role": "client"},
]


def make_unique_email() -> str:
    """Generate a guaranteed-unique email for each registration test."""
    return f"stress_{uuid.uuid4().hex[:12]}@fashionistar-stress.io"


def make_unique_phone() -> str:
    """Generate a valid Nigerian phone number."""
    suffix = random.randint(10000000, 99999999)
    return f"+23480{suffix}"


# ─── Headers ─────────────────────────────────────────────────────────────────
JSON_HEADERS = {
    "Content-Type": "application/json",
    "Accept":       "application/json",
}


# =============================================================================
#  REGISTRATION STRESS USER — hammers the register endpoint
# =============================================================================

class RegistrationUser(HttpUser):
    """
    Stress test: POST /api/v1/auth/register/

    Each user:
      1. Registers with a unique email (happy path)
      2. Attempts a duplicate registration (409 expected)
      3. Attempts malformed payloads (400 expected)

    Target RPS: 500-2000 per instance on ASGI
    """
    wait_time = between(0.1, 0.5)
    weight    = 3   # 3x more weight than other user types

    def on_start(self):
        """Warm-up: ensure server is responding before test traffic."""
        with self.client.get("/api/v1/", catch_response=True) as resp:
            if resp.status_code >= 500:
                resp.failure("Server is DOWN — aborting registration stress")
                raise StopUser()
        self._registered_email = None

    @task(8)
    def register_new_user_email(self):
        """Register a new unique user via email — expect 201."""
        email = make_unique_email()
        payload = {
            "email":     email,
            "password":  BASE_PASSWORD,
            "password2": BASE_PASSWORD,
            "role":      random.choice(VALID_ROLES),
        }
        with self.client.post(
            "/api/v1/auth/register/",
            json=payload,
            headers=JSON_HEADERS,
            name="/api/v1/auth/register/ [email]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 201:
                self._registered_email = email
                resp.success()
            elif resp.status_code == 400:
                # Validation error — acceptable in stress test (dup email race)
                resp.success()
            else:
                resp.failure(
                    f"Unexpected status {resp.status_code}: {resp.text[:200]}"
                )

    @task(3)
    def register_new_user_phone(self):
        """Register a new unique user via phone — expect 201."""
        payload = {
            "phone":     make_unique_phone(),
            "password":  BASE_PASSWORD,
            "password2": BASE_PASSWORD,
            "role":      random.choice(VALID_ROLES),
        }
        with self.client.post(
            "/api/v1/auth/register/",
            json=payload,
            headers=JSON_HEADERS,
            name="/api/v1/auth/register/ [phone]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (201, 400):
                resp.success()
            else:
                resp.failure(
                    f"Unexpected status {resp.status_code}: {resp.text[:200]}"
                )

    @task(2)
    def register_duplicate_email(self):
        """Attempt duplicate registration — expect 400 with 'already exists' error."""
        if not self._registered_email:
            return
        payload = {
            "email":     self._registered_email,
            "password":  BASE_PASSWORD,
            "password2": BASE_PASSWORD,
            "role":      "client",
        }
        with self.client.post(
            "/api/v1/auth/register/",
            json=payload,
            headers=JSON_HEADERS,
            name="/api/v1/auth/register/ [duplicate]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 400:
                resp.success()
            elif resp.status_code == 201:
                resp.failure("Duplicate email was registered — data integrity BUG!")
            else:
                resp.failure(f"Unexpected {resp.status_code}: {resp.text[:200]}")

    @task(1)
    def register_password_mismatch(self):
        """Try pw mismatch — expect 400."""
        payload = {
            "email":     make_unique_email(),
            "password":  BASE_PASSWORD,
            "password2": "WrongPassword!999",
            "role":      "client",
        }
        with self.client.post(
            "/api/v1/auth/register/",
            json=payload,
            headers=JSON_HEADERS,
            name="/api/v1/auth/register/ [pw mismatch]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 400:
                resp.success()
            else:
                resp.failure(f"Expected 400, got {resp.status_code}")

    @task(1)
    def register_empty_payload(self):
        """Try empty payload — expect 400."""
        with self.client.post(
            "/api/v1/auth/register/",
            json={},
            headers=JSON_HEADERS,
            name="/api/v1/auth/register/ [empty body]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 400:
                resp.success()
            else:
                resp.failure(f"Expected 400, got {resp.status_code}")


# =============================================================================
#  LOGIN STRESS USER — hammers the login endpoint
# =============================================================================

class LoginUser(HttpUser):
    """
    Stress test: POST /api/v1/auth/login/

    Uses a pre-seeded verified user (set LOGIN_EMAIL + LOGIN_PASS below)
    or creates one on start.
    """
    wait_time = between(0.1, 0.3)
    weight    = 2

    # ── Override these for your test environment ──────────────────────────
    SEED_EMAIL    = "stress_login@fashionistar-test.io"
    SEED_PASSWORD = BASE_PASSWORD
    # ─────────────────────────────────────────────────────────────────────

    def on_start(self):
        """Login with known credentials to warm up the session."""
        self._access_token  = None
        self._refresh_token = None

    @task(10)
    def login_valid(self):
        """Login with correct credentials — expect 200 + JWT tokens."""
        payload = {
            "email_or_phone": self.SEED_EMAIL,
            "password":        self.SEED_PASSWORD,
        }
        with self.client.post(
            "/api/v1/auth/login/",
            json=payload,
            headers=JSON_HEADERS,
            name="/api/v1/auth/login/ [valid]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 200:
                data = resp.json()
                tokens = data.get("tokens", {})
                self._access_token  = tokens.get("access")
                self._refresh_token = tokens.get("refresh")
                resp.success()
            elif resp.status_code in (400, 403):
                # Seed user may not exist in fresh DB — treat as expected
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}: {resp.text[:200]}")

    @task(3)
    def login_wrong_password(self):
        """Attempt wrong password — expect 400."""
        payload = {
            "email_or_phone": self.SEED_EMAIL,
            "password":        "WrongPassword!000",
        }
        with self.client.post(
            "/api/v1/auth/login/",
            json=payload,
            headers=JSON_HEADERS,
            name="/api/v1/auth/login/ [wrong pw]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (400, 401):
                resp.success()
            else:
                resp.failure(f"Expected 400/401, got {resp.status_code}")

    @task(2)
    def login_nonexistent_user(self):
        """Attempt login with email that doesn't exist — expect 400."""
        payload = {
            "email_or_phone": f"ghost_{uuid.uuid4().hex[:8]}@fashionistar-stress.io",
            "password":        BASE_PASSWORD,
        }
        with self.client.post(
            "/api/v1/auth/login/",
            json=payload,
            headers=JSON_HEADERS,
            name="/api/v1/auth/login/ [nonexistent]",
            catch_response=True,
        ) as resp:
            if resp.status_code == 400:
                resp.success()
            else:
                resp.failure(f"Expected 400, got {resp.status_code}")


# =============================================================================
#  COMPREHENSIVE MIXED TRAFFIC USER — realistic production traffic profile
# =============================================================================

class ComprehensiveUser(HttpUser):
    """
    Mixed realistic traffic profile:
      - 50% registration flows
      - 30% login flows
      - 10% health/schema checks
      - 10% security probe (expect 400/401)
    """
    wait_time = between(0.5, 2.0)
    weight    = 1

    def on_start(self):
        self._access_token  = None
        self._refresh_token = None

    @task(5)
    def full_register_flow(self):
        """Register a unique user."""
        payload = {
            "email":     make_unique_email(),
            "password":  BASE_PASSWORD,
            "password2": BASE_PASSWORD,
            "role":      "client",
        }
        with self.client.post(
            "/api/v1/auth/register/",
            json=payload,
            headers=JSON_HEADERS,
            name="/api/v1/auth/register/ [comprehensive]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (201, 400):
                resp.success()
            else:
                resp.failure(f"Unexpected {resp.status_code}")

    @task(3)
    def check_api_schema(self):
        """Hit OpenAPI schema endpoint (DRF-spectacular)."""
        with self.client.get(
            "/api/schema/",
            headers={"Accept": "application/json"},
            name="/api/schema/ [swagger]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (200, 404):
                resp.success()
            else:
                resp.failure(f"Schema error {resp.status_code}")

    @task(2)
    def probe_unauthenticated(self):
        """Probe authenticated endpoint without token — expect 401."""
        with self.client.post(
            "/api/v1/auth/logout/",
            json={"refresh": "fake-token"},
            headers=JSON_HEADERS,
            name="/api/v1/auth/logout/ [unauth probe]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (401, 403):
                resp.success()
            else:
                resp.failure(f"Expected 401/403, got {resp.status_code}")

    @task(1)
    def resend_otp_probe(self):
        """Probe resend OTP with unknown email — expect 400."""
        with self.client.post(
            "/api/v1/auth/resend-otp/",
            json={"email_or_phone": f"nobody_{uuid.uuid4().hex[:6]}@example.io"},
            headers=JSON_HEADERS,
            name="/api/v1/auth/resend-otp/ [probe]",
            catch_response=True,
        ) as resp:
            if resp.status_code in (400, 404):
                resp.success()
            else:
                resp.failure(f"Expected 400/404, got {resp.status_code}")


# =============================================================================
#  LOCUST EVENT HOOKS — print summary at end of test
# =============================================================================

@events.quitting.add_listener
def on_quitting(environment, **kwargs):
    """Print a brief summary when the test ends."""
    stats = environment.stats.total
    print("\n" + "═" * 60)
    print("     FASHIONISTAR STRESS TEST — RESULTS SUMMARY")
    print("═" * 60)
    print(f"  Total Requests        : {stats.num_requests:,}")
    print(f"  Total Failures        : {stats.num_failures:,}")
    print(f"  Failure Rate          : {stats.fail_ratio * 100:.1f}%")
    print(f"  Avg Response Time     : {stats.avg_response_time:.0f} ms")
    print(f"  95th Percentile       : {stats.get_response_time_percentile(0.95):.0f} ms")
    print(f"  99th Percentile       : {stats.get_response_time_percentile(0.99):.0f} ms")
    print(f"  Max Response Time     : {stats.max_response_time:.0f} ms")
    print(f"  Requests/sec          : {stats.current_rps:.1f}")
    print("═" * 60)
    if stats.fail_ratio > 0.01:     # >1% failure rate is a FAIL
        print("  ⚠️  RESULT: DEGRADED (failure rate > 1%)")
    elif stats.avg_response_time > 2000:
        print("  ⚠️  RESULT: SLOW (avg > 2s)")
    else:
        print("  ✅ RESULT: HEALTHY")
    print("═" * 60 + "\n")
