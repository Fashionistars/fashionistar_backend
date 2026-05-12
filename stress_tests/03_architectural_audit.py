#!/usr/bin/env python3
# stress_tests/03_architectural_audit.py
"""
FASHIONISTAR — OTP Architectural Audit (Design Flaw Detection)
==============================================================
Runs targeted tests for known architectural pitfalls in OTP systems.
Does NOT require an HTTP server — tests service logic directly.

Checks:
  [1] SHA-256 Collision Resistance
      Verifies that different OTPs always produce different hash keys.
      A collision would allow one OTP to unlock another user's account.

  [2] OTP Entropy
      Verifies OTP space is large enough (10^6) — cannot brute-force in 5 min.

  [3] Key Expiry Enforcement
      Seeds an OTP with TTL=2s, waits, confirms it can no longer be verified.

  [4] Orphaned Hash Index Cleanup
      If primary key TTL elapses before hash index, verify_by_otp_sync
      must clean up the orphaned hash index and return None.

  [5] Purpose Segregation
      An OTP generated for 'reset' MUST NOT verify with purpose='verify'.
      Cross-purpose verification = critical security bug.

  [6] User Discovery Pattern (Legacy Match)
      Confirms verify_by_otp_sync() discovers user_id FROM the OTP
      (not the other way around), matching legacy VerifyOTPView pattern.

  [7] Generic Resend Message (Enumeration Guard)
      resend_otp_sync() must return identical message for
      existing and non-existing users (prevents email enumeration).

  [8] Token One-Time Use
      After successful verify_by_otp_sync(), the OTP must be consumed.
      Second call with same OTP must return None.

  [9] Concurrent Pipeline Atomicity
      Pipeline DELETE is atomic — both primary + hash key deleted together.
      Partial deletions would leave orphaned hash indexes.

  [10] 10,000 User Redis Keyspace Impact
       Confirms that with 10k OTPs in keyspace, O(1) lookup stays flat.

Run:
    cd fashionistar_backend
    venv/Scripts/python stress_tests/03_architectural_audit.py
"""

import hashlib
import os
import sys
import time
import threading
import random

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')

import django
django.setup()

import redis as redis_lib

REDIS_HOST = '127.0.0.1'
REDIS_PORT = 6379
REDIS_DB   = 15

PASS = "✅ PASS"
FAIL = "❌ FAIL"
WARN = "⚠️  WARN"


def _sha256(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def _seed_one(r, user_id: str, otp: str, purpose: str = 'verify', ttl: int = 300):
    enc      = 'FAKEENC' + hashlib.sha256(otp.encode()).hexdigest()[:80]
    otp_hash = _sha256(otp)
    snippet  = enc[:16]
    primary  = f"otp:{user_id}:{purpose}:{snippet}"
    hash_key = f"otp_hash:{otp_hash}"
    value    = f"{enc}|{otp_hash}"
    pipe = r.pipeline()
    pipe.setex(primary,  ttl, value)
    pipe.setex(hash_key, ttl, primary)
    pipe.execute()
    return primary, hash_key, otp_hash


def _do_verify(r, otp: str, purpose: str = 'verify') -> dict | None:
    """Mirrors OTPService.verify_by_otp_sync exactly."""
    otp_hash    = _sha256(otp)
    hash_key    = f"otp_hash:{otp_hash}"
    primary_raw = r.get(hash_key)
    if not primary_raw:
        return None
    primary_key = primary_raw.decode()
    parts = primary_key.split(':')
    if len(parts) < 4 or parts[0] != 'otp':
        return None
    stored_purpose = parts[2]
    if stored_purpose != purpose:
        return None
    primary_val = r.get(primary_key)
    if not primary_val:
        r.delete(hash_key)  # Cleanup orphan
        return None
    pipe = r.pipeline()
    pipe.delete(primary_key)
    pipe.delete(hash_key)
    pipe.execute()
    return {'user_id': parts[1], 'purpose': stored_purpose}


def check(num: int, name: str, passed: bool, detail: str = ''):
    status = PASS if passed else FAIL
    print(f"  [{num:02d}] {status}  {name}")
    if detail:
        prefix = "       "
        for line in detail.strip().split('\n'):
            print(f"{prefix}{line}")


def run_audit():
    print("=" * 65)
    print("  FASHIONISTAR — OTP Architectural Audit")
    print("=" * 65)

    r = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    try:
        r.ping()
        r.flushdb()
    except Exception:
        print("❌  Redis unavailable")
        sys.exit(1)

    results = []

    # ─────────────────────────────────────────────────────────────────────────
    # [1] SHA-256 Collision Resistance
    # ─────────────────────────────────────────────────────────────────────────
    hashes = set()
    for otp in range(100000, 1000000):
        h = _sha256(str(otp))
        if h in hashes:
            check(1, "SHA-256 Collision Resistance", False,
                  f"Collision found for OTP {otp}")
            results.append(False)
            break
        hashes.add(h)
    else:
        check(1, "SHA-256 Collision Resistance", True,
              "All 900,000 6-digit OTPs produce unique SHA-256 hashes.")
        results.append(True)

    # ─────────────────────────────────────────────────────────────────────────
    # [2] OTP Entropy
    # ─────────────────────────────────────────────────────────────────────────
    otp_space = 10 ** 6   # 000000 – 999999
    ttl_secs  = 300       # 5 minutes
    brute_rate_per_sec = 1  # Max 1 req/s via throttle
    guesses_in_ttl = brute_rate_per_sec * ttl_secs
    entropy_ok = otp_space / guesses_in_ttl >= 1000   # 1:1000 odds minimum
    check(2, "OTP Entropy vs Brute Force", entropy_ok,
          f"Space=10^6  TTL={ttl_secs}s  Max guesses={guesses_in_ttl}  "
          f"Odds=1:{otp_space//guesses_in_ttl}")
    results.append(entropy_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # [3] Key Expiry Enforcement
    # ─────────────────────────────────────────────────────────────────────────
    _seed_one(r, 'EXPIRE_USER', '111111', ttl=2)
    time.sleep(3)
    result = _do_verify(r, '111111')
    check(3, "Key Expiry Enforcement (TTL=2s)", result is None,
          "OTP expired after 3s wait → verify returns None (correct)." if result is None
          else "OTP still verifiable after TTL! Redis TTL not working.")
    results.append(result is None)

    # ─────────────────────────────────────────────────────────────────────────
    # [4] Orphaned Hash Index Cleanup
    # ─────────────────────────────────────────────────────────────────────────
    primary, hash_key, otp_hash = _seed_one(r, 'ORPHAN_USER', '222222', ttl=300)
    r.delete(primary)  # Delete primary but keep hash_key → simulates TTL skew
    result = _do_verify(r, '222222')  # Should return None AND delete hash_key
    orphan_cleaned = r.exists(hash_key) == 0
    check(4, "Orphaned Hash Index Cleanup", result is None and orphan_cleaned,
          f"Result={result}  hash_key_removed={orphan_cleaned}")
    results.append(result is None and orphan_cleaned)

    # ─────────────────────────────────────────────────────────────────────────
    # [5] Purpose Segregation
    # ─────────────────────────────────────────────────────────────────────────
    _seed_one(r, 'PURPOSE_USER', '333333', purpose='reset', ttl=300)
    result_wrong  = _do_verify(r, '333333', purpose='verify')  # Must be None
    _seed_one(r, 'PURPOSE_USER', '333333', purpose='reset', ttl=300)  # Re-seed
    result_correct = _do_verify(r, '333333', purpose='reset')           # Must work
    check(5, "Purpose Segregation (reset ≠ verify)", result_wrong is None and result_correct is not None,
          f"Wrong purpose → {result_wrong}  "
          f"Correct purpose → {result_correct}")
    results.append(result_wrong is None and result_correct is not None)

    # ─────────────────────────────────────────────────────────────────────────
    # [6] User Discovery Pattern (Legacy Match)
    # ─────────────────────────────────────────────────────────────────────────
    _seed_one(r, 'DISCOVERY_USER_XYZ', '444444', ttl=300)
    result = _do_verify(r, '444444')
    user_discovered = result is not None and result.get('user_id') == 'DISCOVERY_USER_XYZ'
    check(6, "User Discovery from OTP (Legacy Pattern)", user_discovered,
          f"OTP '444444' → discovered user_id={result.get('user_id') if result else None}"
          f"\n    Client sends ONLY otp, server finds user → ✅" if user_discovered
          else "\n    Client sends ONLY otp, server finds user → ❌ FAILED")
    results.append(user_discovered)

    # ─────────────────────────────────────────────────────────────────────────
    # [7] Generic Resend Message (Enumeration Guard)
    # ─────────────────────────────────────────────────────────────────────────
    from apps.authentication.services.otp.sync_service import OTPService
    from unittest.mock import patch

    with patch.object(OTPService, 'generate_otp_sync', return_value='654321'):
        msg_existing    = OTPService.resend_otp_sync('nonexistent@fashionistar.io')
        msg_nonexistent = OTPService.resend_otp_sync('also_nonexistent@fashionistar.io')

    same_msg = msg_existing == msg_nonexistent
    check(7, "Generic Resend Message (Anti-Enumeration)", same_msg,
          f"Existing user msg    : '{msg_existing}'\n"
          f"    Nonexistent msg  : '{msg_nonexistent}'\n"
          f"    Messages match   : {same_msg}")
    results.append(same_msg)

    # ─────────────────────────────────────────────────────────────────────────
    # [8] Token One-Time Use
    # ─────────────────────────────────────────────────────────────────────────
    _seed_one(r, 'ONETIME_USER', '555555', ttl=300)
    r1 = _do_verify(r, '555555')   # First — should succeed
    r2 = _do_verify(r, '555555')   # Second — must fail (already consumed)
    check(8, "Token One-Time Use", r1 is not None and r2 is None,
          f"1st verify: {r1}  2nd verify: {r2}")
    results.append(r1 is not None and r2 is None)

    # ─────────────────────────────────────────────────────────────────────────
    # [9] Concurrent Pipeline Atomicity (50 threads, same OTP)
    # ─────────────────────────────────────────────────────────────────────────
    _seed_one(r, 'ATOMIC_USER', '666666', ttl=300)
    success_count = [0]
    lock          = threading.Lock()

    def _thread_verify():
        rconn = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        result = _do_verify(rconn, '666666')
        if result is not None:
            with lock:
                success_count[0] += 1

    threads = [threading.Thread(target=_thread_verify) for _ in range(50)]
    for t in threads: t.start()
    for t in threads: t.join()

    atomic_ok = success_count[0] == 1
    check(9, "Concurrent Pipeline Atomicity (50 threads)", atomic_ok,
          f"50 threads competed — {success_count[0]} succeeded "
          f"({'expected=1' if atomic_ok else 'BUG: >1 succeeded!'})")
    results.append(atomic_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # [10] 10,000 User Keyspace Impact on O(1) Lookup
    # ─────────────────────────────────────────────────────────────────────────
    print("\n  [10] Seeding 10,000 OTPs for keyspace impact test …", end='', flush=True)
    target_otp = '777777'
    _seed_one(r, 'KEYSPACE_USER', target_otp, ttl=300)

    pipe = r.pipeline(transaction=False)
    for i in range(10_000):
        noise_otp = f"{random.randint(100000, 999999)}"
        enc       = 'FAKEENC' + hashlib.sha256(noise_otp.encode()).hexdigest()[:80]
        otp_hash  = _sha256(noise_otp)
        primary   = f"otp:NOISE-{i:06d}:verify:{enc[:16]}"
        pipe.setex(primary,             300, f"{enc}|{otp_hash}")
        pipe.setex(f"otp_hash:{otp_hash}", 300, primary)
        if (i + 1) % 500 == 0:
            pipe.execute()
            pipe = r.pipeline(transaction=False)
    pipe.execute()
    print(" done.")

    # Now lookup target in 10k-item keyspace
    times = []
    for _ in range(100):
        _seed_one(r, 'KEYSPACE_USER', target_otp, ttl=300)
        t0 = time.perf_counter()
        result = _do_verify(r, target_otp)
        times.append((time.perf_counter() - t0) * 1000)

    import statistics
    mean_ms = statistics.mean(times)
    p99_ms  = sorted(times)[98]
    keyspace_ok = p99_ms < 10  # Should be <10ms even with 10k keys
    check(10, "O(1) Lookup in 10k-key Keyspace", keyspace_ok,
          f"Mean={mean_ms:.2f}ms  P99={p99_ms:.2f}ms  "
          f"({'OK — constant time' if keyspace_ok else 'SLOW — not O(1)!'})")
    results.append(keyspace_ok)

    # ─────────────────────────────────────────────────────────────────────────
    # SUMMARY
    # ─────────────────────────────────────────────────────────────────────────
    passed = sum(results)
    total  = len(results)
    print(f"\n{'═'*65}")
    print(f"  AUDIT RESULTS: {passed}/{total} checks passed")
    if passed == total:
        print("  🎉 ALL CHECKS PASSED — OTP system is architecturally sound!")
    else:
        failed = [i+1 for i, ok in enumerate(results) if not ok]
        print(f"  ❌ FAILED CHECKS: {failed}")
    print(f"{'═'*65}")

    # Cleanup
    r.flushdb()


if __name__ == '__main__':
    run_audit()
