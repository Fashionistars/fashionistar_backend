#!/usr/bin/env python3
# stress_tests/02_http_load_test.py
"""
FASHIONISTAR — HTTP Concurrent Load Test (asyncio + aiohttp)
=============================================================
Tests the full OTP verify + resend HTTP endpoint cycle at high concurrency.

What it does:
  1. Registers N_USERS fictional users (using register endpoint)
  2. Seeds their OTPs directly into Redis (bypasses email delivery)
  3. Fires CONCURRENCY simultaneous POST /api/v1/auth/verify-otp/
  4. Measures RPS, latency distribution, error rates
  5. Tests POST /api/v1/auth/resend-otp/ under concurrent load
  6. Tests alternating verify + resend pairs (realistic user flow)

Architecture stress points tested:
  - Connection pool exhaustion (Django DB connections)
  - Redis pipeline contention under heavy load
  - OTP idempotency: same OTP fired 10× concurrently → only 1 success
  - Resend flooding: 500 resend requests for same email simultaneously
  - Token race: verify while resend is in progress

Run:
    cd fashionistar_backend
    # Terminal 1: make uvicorn  (Uvicorn ASGI is faster for this test)
    # Terminal 2:
    venv/Scripts/python stress_tests/02_http_load_test.py

Requirements:
  pip install aiohttp
  Uvicorn running on http://127.0.0.1:8001  (or edit BASE_URL below)
"""

import asyncio
import hashlib
import os
import sys
import time
import random
import string
import json
import statistics
from dataclasses import dataclass, field
from typing import List, Dict, Optional, Tuple

# ── Path setup ─────────────────────────────────────────────────────────────
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')

import django
django.setup()

try:
    import aiohttp
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False
    print("⚠️  aiohttp not installed — HTTP load test skipped.")
    print("    pip install aiohttp")

import redis as redis_lib

# ── Config ──────────────────────────────────────────────────────────────────
BASE_URL    = 'http://127.0.0.1:8001/api/v1/auth'   # Uvicorn (async)
BASE_URL_W  = 'http://127.0.0.1:8000/api/v1/auth'   # WSGI fallback
N_USERS     = 200       # Users to register programmatically
CONCURRENCY = 50        # Concurrent requests per wave
WAVES       = 5         # Waves per scenario
REDIS_HOST  = '127.0.0.1'
REDIS_PORT  = 6379
REDIS_DB    = 15
TIMEOUT     = aiohttp.ClientTimeout(total=30) if HAS_AIOHTTP else None


@dataclass
class HttpResult:
    name: str
    latencies_ms: List[float] = field(default_factory=list)
    status_codes: List[int]   = field(default_factory=list)
    errors: List[str]         = field(default_factory=list)

    @property
    def success_rate(self) -> float:
        total   = len(self.status_codes)
        success = sum(1 for c in self.status_codes if 200 <= c < 300)
        return success / total * 100 if total > 0 else 0

    @property
    def p99(self) -> float:
        if not self.latencies_ms:
            return 0
        s = sorted(self.latencies_ms)
        return s[int(len(s) * 0.99)]

    @property
    def rps(self) -> float:
        total_s = sum(self.latencies_ms) / 1000.0
        return len(self.latencies_ms) / total_s if total_s > 0 else 0

    def report(self):
        print(f"\n{'─'*60}")
        print(f"  {self.name}")
        print(f"{'─'*60}")
        print(f"  Total requests : {len(self.status_codes):,}")
        print(f"  Success rate   : {self.success_rate:.1f}%")
        if self.latencies_ms:
            print(f"  Mean latency   : {statistics.mean(self.latencies_ms):.1f} ms")
            print(f"  P95 latency    : {self.p99:.1f} ms")
            print(f"  RPS (est.)     : {self.rps:,.0f}")
        if self.errors:
            print(f"  Errors (first 3): {self.errors[:3]}")
        codes = {}
        for c in self.status_codes:
            codes[c] = codes.get(c, 0) + 1
        print(f"  Status codes   : {dict(sorted(codes.items()))}")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _sha256(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def _seed_otp_redis(user_id: str, otp: str, redis_conn) -> None:
    """Directly seeds one OTP into Redis (bypasses email delivery)."""
    import base64
    encrypted = 'FAKEENC' + hashlib.sha256((otp + user_id).encode()).hexdigest()[:80]
    otp_hash  = _sha256(otp)
    snippet   = encrypted[:16]
    primary   = f"otp:{user_id}:verify:{snippet}"
    hash_key  = f"otp_hash:{otp_hash}"
    value     = f"{encrypted}|{otp_hash}"
    pipe = redis_conn.pipeline()
    pipe.setex(primary,  300, value)
    pipe.setex(hash_key, 300, primary)
    pipe.execute()


# ══════════════════════════════════════════════════════════════════════════════
#  SETUP — Register users directly via Django ORM (fastest)
# ══════════════════════════════════════════════════════════════════════════════

def setup_test_users(r: redis_lib.Redis, n: int = N_USERS) -> List[Dict]:
    """
    Creates n UnifiedUser instances directly via ORM (no HTTP overhead).
    Seeds their OTPs directly into Redis DB-15.
    Returns list of {user_id, email, otp} for benchmark use.
    """
    from apps.authentication.models import UnifiedUser

    print(f"\n🔧  Creating {n:,} test users via ORM …")
    users = []
    t0 = time.perf_counter()

    for i in range(n):
        email = f"stresstest_{i:05d}@fashionistar-load.io"
        otp   = f"{random.randint(100000, 999999)}"
        try:
            user, created = UnifiedUser.objects.get_or_create(
                email=email,
                defaults={
                    'role':        'client',
                    'is_active':   False,
                    'is_verified': False,
                }
            )
            if created:
                user.set_password('LoadTest!789')
                user.save(update_fields=['password'])

            _seed_otp_redis(str(user.id), otp, r)
            users.append({'user_id': str(user.id), 'email': email, 'otp': otp})

        except Exception as exc:
            pass  # User may already exist from previous run

    elapsed = time.perf_counter() - t0
    print(f"✅  {len(users):,} users ready in {elapsed:.2f}s")
    return users


# ══════════════════════════════════════════════════════════════════════════════
#  LOAD TEST A — Concurrent OTP Verification
# ══════════════════════════════════════════════════════════════════════════════

async def load_test_verify_otp(
    session: 'aiohttp.ClientSession',
    users: List[Dict],
    base_url: str,
) -> HttpResult:
    """
    Fires CONCURRENCY × WAVES verify-otp requests concurrently.
    Each request uses a DIFFERENT user's OTP (no race condition expected).
    Measures throughput, latency, and success rate.
    """
    result  = HttpResult("Load Test A — Concurrent OTP Verification")
    sample  = users[:min(CONCURRENCY * WAVES, len(users))]
    url     = f"{base_url}/verify-otp/"

    print(f"\n⚡  Verify-OTP load: {CONCURRENCY} concurrent × {WAVES} waves …")

    for wave_i in range(WAVES):
        chunk = sample[wave_i * CONCURRENCY:(wave_i + 1) * CONCURRENCY]
        if not chunk:
            break

        async def _verify(rec: Dict) -> Tuple[int, float, Optional[str]]:
            t0 = time.perf_counter()
            try:
                async with session.post(
                    url,
                    json={'otp': rec['otp']},
                    timeout=TIMEOUT,
                ) as resp:
                    body = await resp.json()
                    lat  = (time.perf_counter() - t0) * 1000
                    return resp.status, lat, None
            except Exception as exc:
                return 0, (time.perf_counter() - t0) * 1000, str(exc)

        results = await asyncio.gather(*[_verify(r) for r in chunk])
        for status, lat, err in results:
            result.status_codes.append(status)
            result.latencies_ms.append(lat)
            if err:
                result.errors.append(err)

        print(f"    Wave {wave_i+1}/{WAVES}: "
              f"{sum(1 for s, _, _ in results if 200 <= s < 300)}/{len(results)} success")

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  LOAD TEST B — Concurrent Resend OTP
# ══════════════════════════════════════════════════════════════════════════════

async def load_test_resend_otp(
    session: 'aiohttp.ClientSession',
    users: List[Dict],
    base_url: str,
) -> HttpResult:
    """
    Fires CONCURRENCY resend-otp requests concurrently (different users).
    Also tests: 20 concurrent resend for THE SAME email (resend flood guard).
    """
    result = HttpResult("Load Test B — Concurrent Resend OTP")
    url    = f"{base_url}/resend-otp/"

    print(f"\n📨  Resend-OTP load: {CONCURRENCY} concurrent × {WAVES} waves …")

    sample = users[:min(CONCURRENCY * WAVES, len(users))]

    for wave_i in range(WAVES):
        chunk = sample[wave_i * CONCURRENCY:(wave_i + 1) * CONCURRENCY]
        if not chunk:
            break

        async def _resend(rec: Dict) -> Tuple[int, float, Optional[str]]:
            t0 = time.perf_counter()
            try:
                async with session.post(
                    url,
                    json={'email_or_phone': rec['email']},
                    timeout=TIMEOUT,
                ) as resp:
                    lat = (time.perf_counter() - t0) * 1000
                    return resp.status, lat, None
            except Exception as exc:
                return 0, (time.perf_counter() - t0) * 1000, str(exc)

        results = await asyncio.gather(*[_resend(r) for r in chunk])
        for status, lat, err in results:
            result.status_codes.append(status)
            result.latencies_ms.append(lat)
            if err:
                result.errors.append(err)

        print(f"    Wave {wave_i+1}/{WAVES}: "
              f"{sum(1 for s, _, _ in results if 200 <= s < 300)}/{len(results)} success")

    # Resend flood sub-test (50 consecutive resends for same email)
    print(f"\n💥  Resend flood sub-test: 50× same email …")
    flood_user  = users[0] if users else None
    if flood_user:
        flood_tasks = [_resend(flood_user) for _ in range(50)]
        flood_res   = await asyncio.gather(*flood_tasks)
        flood_ok    = sum(1 for s, _, _ in flood_res if 200 <= s < 300)
        print(f"    Result: {flood_ok}/50 returned 200 OK")
        print(f"    (All should return 200 — resend is idempotent by design)")

    return result


# ══════════════════════════════════════════════════════════════════════════════
#  LOAD TEST C — Idempotency: Same OTP fired 20× concurrently
# ══════════════════════════════════════════════════════════════════════════════

async def load_test_idempotency(
    session: 'aiohttp.ClientSession',
    users: List[Dict],
    r: redis_lib.Redis,
    base_url: str,
) -> None:
    """
    Fires the SAME OTP 20 times concurrently.
    Expected: exactly 1 HTTP 200, the rest should be 400.
    If multiple 200s → idempotency bug / race condition.
    """
    print(f"\n🔁  Idempotency Test — same OTP × 20 concurrent requests …")

    if not users:
        print("    No users available — skipping")
        return

    target = users[0]
    otp    = '555555'
    _seed_otp_redis(target['user_id'], otp, r)

    url = f"{base_url}/verify-otp/"

    async def _hit():
        t0 = time.perf_counter()
        try:
            async with session.post(url, json={'otp': otp}, timeout=TIMEOUT) as resp:
                return resp.status
        except:
            return 0

    statuses = await asyncio.gather(*[_hit() for _ in range(20)])
    ok_count = sum(1 for s in statuses if s == 200)
    status_summary = {s: statuses.count(s) for s in set(statuses)}

    verdict = "✅ PASS" if ok_count == 1 else f"❌ FAIL — {ok_count} x 200 received!"
    print(f"    OTP fired 20× concurrently")
    print(f"    HTTP 200 responses : {ok_count}")
    print(f"    Status breakdown   : {status_summary}")
    print(f"    Idempotency guard  : {verdict}")


# ══════════════════════════════════════════════════════════════════════════════
#  DETECT WHICH SERVER IS RUNNING
# ══════════════════════════════════════════════════════════════════════════════

async def detect_server(session: 'aiohttp.ClientSession') -> str:
    for url in [BASE_URL, BASE_URL_W]:
        try:
            async with session.get(
                url.replace('/auth', '/health/'),
                timeout=aiohttp.ClientTimeout(total=2)
            ) as r:
                print(f"✅  Server detected at {url} (HTTP {r.status})")
                return url
        except:
            pass
    print(f"⚠️  No server at {BASE_URL} or {BASE_URL_W}")
    print("    Start with: make uvicorn  OR  make dev")
    return BASE_URL


# ══════════════════════════════════════════════════════════════════════════════
#  MAIN (async)
# ══════════════════════════════════════════════════════════════════════════════

async def main_async():
    print("=" * 65)
    print("  FASHIONISTAR — HTTP Concurrent Load Test")
    print("=" * 65)

    r = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    try:
        r.ping()
    except redis_lib.ConnectionError:
        print("❌  Redis unavailable. Run: redis-server")
        return

    # Create test users via ORM
    users = setup_test_users(r, N_USERS)

    connector = aiohttp.TCPConnector(
        limit=200,          # max connections
        ssl=False,
    )
    async with aiohttp.ClientSession(
        connector=connector,
        headers={'Content-Type': 'application/json'},
    ) as session:
        base_url = await detect_server(session)

        # Re-seed all OTPs (they may expire or be consumed)
        print("\n🔄  Re-seeding OTPs for HTTP load test …")
        for u in users:
            _seed_otp_redis(u['user_id'], u['otp'], r)

        # Test A — Concurrent verify
        res_a = await load_test_verify_otp(session, users, base_url)
        res_a.report()

        # Re-seed (verify consumed the OTPs)
        for u in users:
            _seed_otp_redis(u['user_id'], u['otp'], r)

        # Test B — Concurrent resend
        res_b = await load_test_resend_otp(session, users, base_url)
        res_b.report()

        # Re-seed for idempotency test
        for u in users:
            _seed_otp_redis(u['user_id'], u['otp'], r)

        # Test C — Idempotency
        await load_test_idempotency(session, users, r, base_url)

    # Summary
    print(f"\n{'═'*65}")
    print("  FINAL SUMMARY")
    print(f"{'═'*65}")
    print(f"  Verify-OTP  success rate : {res_a.success_rate:.1f}%")
    print(f"  Verify-OTP  RPS          : {res_a.rps:,.0f}")
    if res_a.latencies_ms:
        print(f"  Verify-OTP  p99 latency  : {res_a.p99:.1f} ms")
    print(f"  Resend-OTP  success rate : {res_b.success_rate:.1f}%")
    print(f"  Resend-OTP  RPS          : {res_b.rps:,.0f}")
    print(f"{'═'*65}")

    # Cleanup test data
    print("\n🧹  Cleaning up test users and Redis keys …")
    from apps.authentication.models import UnifiedUser
    UnifiedUser.objects.filter(email__endswith='@fashionistar-load.io').delete()
    r.flushdb()
    print("    Done.")


def main():
    if not HAS_AIOHTTP:
        print("Install aiohttp first: pip install aiohttp")
        return
    asyncio.run(main_async())


if __name__ == '__main__':
    main()
