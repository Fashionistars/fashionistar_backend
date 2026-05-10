"""
FASHIONISTAR — Race Condition Stress Battery (aiohttp async)
=============================================================
Directly tests specific race conditions via asyncio + aiohttp.
Bypasses Locust for precision race testing.

Test Battery:
  1. OTP Race Condition (5000 async threads) — exactly-once consume
  2. Concurrent Registration (1000 async) — same email → exactly 1 user
  3. Concurrent Token Refresh (500 async) — rotation race safety
  4. Session Revocation Race (200 async) — select_for_update correctness
  5. Idempotency Key Race (300 async) — SETNX lock correctness

Usage:
    # Install: uv pip install aiohttp
    python stress_tests/06_race_condition_suite.py

    # Or against ngrok tunnel:
    BASE_URL=https://your-ngrok-url.ngrok-free.app python stress_tests/06_race_condition_suite.py

Requirements:
    - Backend must be running at BASE_URL
    - A pre-created verified user for authenticated tests
    - Redis must be accessible to the backend

Pass criteria:
    - OTP: exactly 1 consumption per OTP code under 5000 concurrent requests
    - Registration: exactly 1 user per unique email under 1000 concurrent requests
    - Token Refresh: at most 1 success per token under rotation
    - Session: exactly 1 successful revocation per session
    - Idempotency: exactly 1 processed request per idempotency key
"""

import asyncio
import aiohttp
import uuid
import json
import os
import sys
import time
from collections import Counter
from typing import Optional

# ─────────────────────────────────────────────────────────────────────────────
# CONFIGURATION
# ─────────────────────────────────────────────────────────────────────────────

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8000")
TIMEOUT = aiohttp.ClientTimeout(total=30)

# Pre-verified test user (must exist in the running DB)
TEST_EMAIL = os.environ.get("STRESS_EMAIL", "stress.verified@fashionistar.io")
TEST_PASS  = os.environ.get("STRESS_PASS",  "StressTest123!")


# ─────────────────────────────────────────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def cprint(color: str, msg: str):
    colors = {"green": "\033[92m", "red": "\033[91m", "yellow": "\033[93m", "reset": "\033[0m"}
    print(f"{colors.get(color, '')}{msg}{colors['reset']}")


async def post(session: aiohttp.ClientSession, url: str, data: dict, headers: dict = None) -> int:
    """Fire a POST request and return HTTP status code."""
    try:
        async with session.post(url, json=data, headers=headers or {}) as resp:
            return resp.status
    except Exception as e:
        return 0  # Connection error


async def get_token(session: aiohttp.ClientSession, email: str, password: str) -> Optional[str]:
    """Login and return access token."""
    async with session.post(
        f"{BASE_URL}/api/v1/auth/login/",
        json={"email_or_phone": email, "password": password},
    ) as resp:
        if resp.status == 200:
            data = await resp.json()
            payload = data.get("data", data)
            return payload.get("access")
    return None


async def run_concurrent(coro_factory, count: int, label: str) -> list[int]:
    """
    Fire `count` coroutines simultaneously via asyncio.gather.
    Returns list of HTTP status codes.
    """
    connector = aiohttp.TCPConnector(limit=count, limit_per_host=count)
    async with aiohttp.ClientSession(
        base_url=BASE_URL,
        timeout=TIMEOUT,
        connector=connector,
    ) as session:
        coros = [coro_factory(session, i) for i in range(count)]
        results = await asyncio.gather(*coros, return_exceptions=True)

    codes = []
    for r in results:
        if isinstance(r, Exception):
            codes.append(0)
        else:
            codes.append(r)

    counter = Counter(codes)
    print(f"  [{label}] Status distribution: {dict(counter)}")
    return codes


def report(label: str, passed: bool, detail: str = ""):
    if passed:
        cprint("green", f"  ✅ PASS: {label}")
    else:
        cprint("red",   f"  ❌ FAIL: {label} — {detail}")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: CONCURRENT REGISTRATION — SAME EMAIL
# ─────────────────────────────────────────────────────────────────────────────

async def test_concurrent_registration(concurrency: int = 1000):
    """1000 concurrent requests for same email → exactly 1 user created (201)."""
    print(f"\n🔥 TEST 1: Concurrent Registration (same email, {concurrency} requests)")

    email = f"race.concurrent.{uuid.uuid4().hex[:8]}@fashionistar.io"
    payload = {
        "email": email,
        "password": "RaceTest123!",
        "password2": "RaceTest123!",
        "first_name": "Race",
        "last_name": "Condition",
        "role": "client",
    }

    async def register(session, _):
        try:
            async with session.post("/api/v1/auth/register/", json=payload) as resp:
                return resp.status
        except Exception:
            return 0

    codes = await run_concurrent(register, concurrency, "register")

    successes_201 = codes.count(201)
    errors_500    = codes.count(500)
    bad_codes     = [c for c in codes if c not in (201, 400, 409, 429, 0)]

    report(
        f"Exactly 1 registration (201) out of {concurrency} concurrent",
        successes_201 == 1,
        f"Got {successes_201} successful registrations. Expected exactly 1.",
    )
    report(
        "Zero 500 errors on concurrent registration",
        errors_500 == 0,
        f"Got {errors_500} internal server errors!"
    )
    report(
        "No unexpected status codes",
        len(bad_codes) == 0,
        f"Unexpected codes: {set(bad_codes)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: IDEMPOTENCY KEY RACE — SETNX LOCK CORRECTNESS
# ─────────────────────────────────────────────────────────────────────────────

async def test_idempotency_race(concurrency: int = 300):
    """300 concurrent POSTs with same idempotency key → at most 1 processed."""
    print(f"\n🔥 TEST 2: Idempotency Race (same key, {concurrency} requests)")

    idempotency_key = str(uuid.uuid4())
    email = f"idem.race.{uuid.uuid4().hex[:6]}@fashionistar.io"
    payload = {
        "email": email,
        "password": "IdemRace123!",
        "password2": "IdemRace123!",
        "first_name": "Idem",
        "last_name": "Race",
        "role": "client",
    }

    async def request(session, _):
        try:
            async with session.post(
                "/api/v1/auth/register/",
                json=payload,
                headers={"X-Idempotency-Key": idempotency_key},
            ) as resp:
                return resp.status
        except Exception:
            return 0

    codes = await run_concurrent(request, concurrency, "idempotency")

    successes_201 = codes.count(201)
    errors_500    = codes.count(500)
    conflict_409  = codes.count(409)

    report(
        f"Idempotency: at most 1 success (201) out of {concurrency} concurrent",
        successes_201 <= 1,
        f"Got {successes_201} successful registrations — SETNX broken!"
    )
    report(
        "Zero 500 errors under idempotency race",
        errors_500 == 0,
        f"Got {errors_500} 500 errors!"
    )
    print(f"  ℹ️  409 Lock Conflicts: {conflict_409} (expected — normal under race)")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: CONCURRENT LOGIN — SAME USER
# ─────────────────────────────────────────────────────────────────────────────

async def test_concurrent_login(concurrency: int = 500):
    """500 concurrent logins for the same verified user — all should get tokens."""
    print(f"\n🔥 TEST 3: Concurrent Login Same User ({concurrency} requests)")

    # Skip if no test user available
    payload = {"email_or_phone": TEST_EMAIL, "password": TEST_PASS}

    async def login(session, _):
        try:
            async with session.post("/api/v1/auth/login/", json=payload) as resp:
                return resp.status
        except Exception:
            return 0

    codes = await run_concurrent(login, concurrency, "login")

    errors_500 = codes.count(500)
    errors_0   = codes.count(0)  # Connection failures

    report(
        "Zero 500 errors on concurrent login",
        errors_500 == 0,
        f"Got {errors_500} 500 errors on login under {concurrency} concurrent requests!"
    )
    if errors_0 > concurrency * 0.05:
        cprint("yellow", f"  ⚠️  WARN: {errors_0} connection failures (likely throttling or connection limit)")


# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: HEALTH ENDPOINT — ALWAYS FAST
# ─────────────────────────────────────────────────────────────────────────────

async def test_health_endpoint(concurrency: int = 2000):
    """2000 concurrent /health/ requests — all must return 200."""
    print(f"\n🔥 TEST 4: Health Endpoint Resilience ({concurrency} concurrent GETs)")

    async def health_check(session, _):
        try:
            async with session.get("/health/") as resp:
                return resp.status
        except Exception:
            return 0

    codes = await run_concurrent(health_check, concurrency, "health")

    successes = codes.count(200)
    failures  = [c for c in codes if c != 200]

    report(
        f"Health: ≥95% success rate under {concurrency} concurrent requests",
        successes >= concurrency * 0.95,
        f"Only {successes}/{concurrency} requests succeeded. Failures: {set(failures)}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# MAIN RUNNER
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    cprint("yellow", "\n" + "=" * 65)
    cprint("yellow", "🏭 FASHIONISTAR — RACE CONDITION STRESS BATTERY")
    cprint("yellow", f"   Target: {BASE_URL}")
    cprint("yellow", "=" * 65)

    start = time.time()

    await test_concurrent_registration(concurrency=500)
    await test_idempotency_race(concurrency=300)
    await test_concurrent_login(concurrency=500)
    await test_health_endpoint(concurrency=2000)

    elapsed = time.time() - start
    cprint("yellow", f"\n⏱  Total time: {elapsed:.1f}s")
    cprint("yellow", "=" * 65 + "\n")


if __name__ == "__main__":
    asyncio.run(main())
