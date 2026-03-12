#!/usr/bin/env python3
# stress_tests/01_redis_benchmark.py
"""
FASHIONISTAR — Redis O(1) Hash Index vs SCAN Benchmark
=======================================================
Seeds 10,000 OTP records then benchmarks three strategies:

  A — O(1) hash index lookup  (verify_by_otp_sync path)  [READ-ONLY mode]
  B — KEYS prefix scan        (legacy verify_otp_sync)    [READ-ONLY mode]
  C — Full verify+delete      (real production flow)
  D — Race condition guard    (50 threads, same OTP)
  E — Idempotency check       (double verify sequential)

Run:
    cd fashionistar_backend
    venv/Scripts/python stress_tests/01_redis_benchmark.py
"""

import asyncio, hashlib, os, sys, time, statistics, random, threading
from dataclasses import dataclass, field
from typing import List, Dict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.config.development')

import django
django.setup()

import redis as redis_lib

REDIS_HOST  = '127.0.0.1'
REDIS_PORT  = 6379
REDIS_DB    = 15       # Isolated test DB
OTP_TTL     = 300
N_USERS     = 10_000
SAMPLE_SIZE = 500      # Ops to measure per benchmark


@dataclass
class BenchmarkResult:
    name: str
    latencies_ms: List[float] = field(default_factory=list)

    def _require_data(self):
        if not self.latencies_ms:
            return False
        return True

    @property
    def p50(self):
        return statistics.median(self.latencies_ms) if self._require_data() else 0

    @property
    def p95(self):
        if not self.latencies_ms: return 0
        s = sorted(self.latencies_ms)
        return s[int(len(s) * 0.95)]

    @property
    def p99(self):
        if not self.latencies_ms: return 0
        s = sorted(self.latencies_ms)
        return s[int(len(s) * 0.99)]

    @property
    def mean(self):
        return statistics.mean(self.latencies_ms) if self._require_data() else 0

    @property
    def rps(self):
        if not self.latencies_ms: return 0
        total_s = sum(self.latencies_ms) / 1000.0
        return len(self.latencies_ms) / total_s if total_s > 0 else 0

    def report(self):
        print(f"\n{'─'*58}")
        print(f"  {self.name}")
        print(f"{'─'*58}")
        if not self.latencies_ms:
            print("  (no data)")
            return
        print(f"  Samples : {len(self.latencies_ms):,}")
        print(f"  Mean    : {self.mean:.3f} ms")
        print(f"  P50     : {self.p50:.3f} ms")
        print(f"  P95     : {self.p95:.3f} ms")
        print(f"  P99     : {self.p99:.3f} ms")
        print(f"  RPS est.: {self.rps:,.0f} req/s")


def _sha256(plain: str) -> str:
    return hashlib.sha256(plain.encode()).hexdigest()


def _fake_enc(otp: str) -> str:
    return 'FAKEENC' + hashlib.sha256(otp.encode()).hexdigest()[:80]


def seed_otp_records(r: redis_lib.Redis, n: int = N_USERS) -> List[Dict]:
    """Seeds n OTP records. Returns list of seed data for benchmarks."""
    print(f"\n🌱  Seeding {n:,} OTP records into Redis DB-15 …", flush=True)
    pipe  = r.pipeline(transaction=False)
    seeds = []
    t0    = time.perf_counter()

    for i in range(n):
        user_id   = f"FSTR-USER-{i:06d}"
        # Use deterministic OTP based on index so duplicates don't create hash collisions
        otp       = str(100000 + i).zfill(6)   # 100000, 100001, … unique OTPs
        enc       = _fake_enc(otp)
        otp_hash  = _sha256(otp)
        snippet   = enc[:16]
        primary   = f"otp:{user_id}:verify:{snippet}"
        hash_key  = f"otp_hash:{otp_hash}"
        value     = f"{enc}|{otp_hash}"

        pipe.setex(primary,   OTP_TTL, value)
        pipe.setex(hash_key,  OTP_TTL, primary)

        seeds.append({
            'user_id':     user_id,
            'otp':         otp,
            'primary_key': primary,
            'hash_key':    hash_key,
        })

        if (i + 1) % 500 == 0:
            pipe.execute()
            pipe = r.pipeline(transaction=False)

    pipe.execute()
    elapsed = time.perf_counter() - t0
    total_keys = r.dbsize()
    print(f"✅  Seeded {n:,} records in {elapsed:.2f}s  ({n/elapsed:,.0f} writes/s)")
    print(f"    Total keys in Redis DB-15: {total_keys:,}")
    return seeds


def benchmark_o1_readonly(r: redis_lib.Redis, seeds: List[Dict]) -> BenchmarkResult:
    """
    READ-ONLY benchmark of O(1) hash index.
    Does GET otp_hash: + GET primary.  No DELETE.
    Measures pure lookup latency unchanged by keyspace size.
    """
    result = BenchmarkResult("A — O(1) SHA256 Hash Index [READ-ONLY, 10k keyspace]")
    sample = random.sample(seeds, min(SAMPLE_SIZE, len(seeds)))
    print(f"\n⚡  Benchmarking O(1) hash-index GET ({len(sample):,} samples) …", flush=True)

    for rec in sample:
        otp_hash = _sha256(rec['otp'])
        hash_key = f"otp_hash:{otp_hash}"
        t0 = time.perf_counter()
        primary_raw = r.get(hash_key)
        if primary_raw:
            r.get(primary_raw.decode())   # TTL guard GET (mirrors prod)
        elapsed_ms = (time.perf_counter() - t0) * 1000
        result.latencies_ms.append(elapsed_ms)

    return result


def benchmark_scan_readonly(r: redis_lib.Redis, seeds: List[Dict]) -> BenchmarkResult:
    """
    READ-ONLY benchmark of KEYS prefix scan.
    KEYS otp:{user_id}:verify:* then GET.  No DELETE.
    Shows how this degrades vs O(1) as keyspace grows.
    """
    result = BenchmarkResult("B — KEYS Prefix Scan [READ-ONLY, 10k keyspace, LEGACY]")
    sample = random.sample(seeds, min(200, len(seeds)))  # 200 — KEYS is slow
    print(f"\n🐢  Benchmarking KEYS scan ({len(sample):,} samples) …", flush=True)

    for rec in sample:
        user_id = rec['user_id']
        pattern = f"otp:{user_id}:verify:*"
        t0 = time.perf_counter()
        keys = r.keys(pattern)
        for key in keys:
            r.get(key)   # read only
        elapsed_ms = (time.perf_counter() - t0) * 1000
        result.latencies_ms.append(elapsed_ms)

    return result


def benchmark_full_verify(r: redis_lib.Redis, seeds: List[Dict]) -> BenchmarkResult:
    """
    Full production verify_by_otp_sync() path including DEL.
    Measures end-to-end latency including atomic cleanup.
    """
    result = BenchmarkResult("C — Full Verify + Atomic Del (O(1) production path)")
    # Take a fresh batch that hasn't been consumed
    sample = seeds[-min(SAMPLE_SIZE, len(seeds)):]
    print(f"\n🔥  Full verify+delete ({len(sample):,} samples) …", flush=True)

    for rec in sample:
        otp      = rec['otp']
        otp_hash = _sha256(otp)
        hash_key = f"otp_hash:{otp_hash}"

        t0 = time.perf_counter()
        pk_raw = r.get(hash_key)
        if pk_raw:
            pk  = pk_raw.decode()
            val = r.get(pk)
            if val:
                pipe = r.pipeline()
                pipe.delete(pk)
                pipe.delete(hash_key)
                pipe.execute()
        elapsed_ms = (time.perf_counter() - t0) * 1000
        result.latencies_ms.append(elapsed_ms)

    return result


def benchmark_race_condition(r: redis_lib.Redis):
    """50 threads race to verify the SAME OTP — only 1 must win."""
    print(f"\n🏁  Race Condition Test (50 threads, same OTP) …", flush=True)

    otp      = '987654'
    enc      = _fake_enc(otp)
    otp_hash = _sha256(otp)
    snippet  = enc[:16]
    primary  = f"otp:RACE_USER:verify:{snippet}"
    hash_key = f"otp_hash:{otp_hash}"
    r.setex(primary,  300, f"{enc}|{otp_hash}")
    r.setex(hash_key, 300, primary)

    success_count = [0]
    lock          = threading.Lock()

    def _verify_thread():
        rconn = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
        h     = _sha256(otp)
        hk    = f"otp_hash:{h}"

        pk_raw = rconn.get(hk)
        if not pk_raw:
            return
        pk  = pk_raw.decode()
        val = rconn.get(pk)
        if not val:
            return

        # Use WATCH + MULTI for optimistic locking (mirrors Redis pipeline atomicity)
        pipe = rconn.pipeline(transaction=True)
        try:
            pipe.watch(pk, hk)
            pipe.multi()
            pipe.delete(pk)
            pipe.delete(hk)
            res = pipe.execute()   # WatchError if concurrent modification
            if res[0] == 1:        # 1 = key was deleted (not pre-deleted)
                with lock:
                    success_count[0] += 1
        except redis_lib.WatchError:
            pass  # Lost the race — correct behaviour

    threads = [threading.Thread(target=_verify_thread) for _ in range(50)]
    for t in threads: t.start()
    for t in threads: t.join()

    passed = success_count[0] == 1
    status = "✅ PASS" if passed else f"❌ FAIL — {success_count[0]} wins!"
    print(f"    50 threads competed → {success_count[0]} successful verify")
    print(f"    Race Condition Guard: {status}")
    return passed


def benchmark_idempotency(r: redis_lib.Redis):
    """Verify same OTP twice — 2nd must fail (one-time use)."""
    print(f"\n🔁  Idempotency Test (same OTP × 2) …", flush=True)

    otp      = '123654'
    enc      = _fake_enc(otp)
    otp_hash = _sha256(otp)
    snippet  = enc[:16]
    primary  = f"otp:IDEM_USER:verify:{snippet}"
    hash_key = f"otp_hash:{otp_hash}"
    r.setex(primary,  300, f"{enc}|{otp_hash}")
    r.setex(hash_key, 300, primary)

    def _do(attempt):
        pk_raw = r.get(hash_key)
        if not pk_raw:
            return False
        pk  = pk_raw.decode()
        val = r.get(pk)
        if not val:
            r.delete(hash_key)
            return False
        pipe = r.pipeline()
        pipe.delete(pk)
        pipe.delete(hash_key)
        pipe.execute()
        return True

    r1 = _do(1)
    r2 = _do(2)
    passed = r1 and not r2
    status = "✅ PASS" if passed else f"❌ FAIL"
    print(f"    1st verify: {r1}  |  2nd verify: {r2}")
    print(f"    Idempotency Guard: {status}")
    return passed


def main():
    print("=" * 60)
    print("  FASHIONISTAR — Redis O(1) vs SCAN Benchmark")
    print("=" * 60)

    r = redis_lib.Redis(host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB)
    try:
        r.ping()
    except redis_lib.ConnectionError:
        print("❌  Redis not running. Start with: redis-server")
        sys.exit(1)

    r.flushdb()   # Clean slate
    print(f"✅  Connected to Redis DB-{REDIS_DB} (fresh start)")

    # ── Phase 1: Seed 10k records ──
    seeds = seed_otp_records(r, N_USERS)

    # ── Benchmark A: O(1) READ-ONLY ──
    res_a = benchmark_o1_readonly(r, seeds)
    res_a.report()

    # ── Benchmark B: SCAN READ-ONLY ──
    res_b = benchmark_scan_readonly(r, seeds)
    res_b.report()

    # ── Benchmark C: Full verify+delete ──
    res_c = benchmark_full_verify(r, seeds)
    res_c.report()

    # ── Race Condition ──
    race_ok = benchmark_race_condition(r)

    # ── Idempotency ──
    idem_ok = benchmark_idempotency(r)

    # ── Summary ──
    print(f"\n{'═'*60}")
    print("  FASHIONISTAR OTP BENCHMARK — SUMMARY")
    print(f"{'═'*60}")
    print(f"  Keyspace size        : {N_USERS:,} OTP records")
    print(f"")
    print(f"  O(1) hash lookup")
    print(f"    Mean               : {res_a.mean:.3f} ms")
    print(f"    P99                : {res_a.p99:.3f} ms")
    print(f"    est. RPS           : {res_a.rps:,.0f}")
    print(f"")
    if res_b.latencies_ms:
        print(f"  KEYS scan (legacy)")
        print(f"    Mean               : {res_b.mean:.3f} ms")
        print(f"    P99                : {res_b.p99:.3f} ms")
        print(f"    est. RPS           : {res_b.rps:,.0f}")
        if res_a.mean > 0 and res_b.mean > 0:
            speedup = res_b.mean / res_a.mean
            print(f"    Speedup (O1/SCAN)  : {speedup:.1f}×")
    print(f"")
    print(f"  Full verify+delete")
    print(f"    Mean               : {res_c.mean:.3f} ms")
    print(f"    P99                : {res_c.p99:.3f} ms")
    print(f"    est. RPS           : {res_c.rps:,.0f}")
    print(f"")
    print(f"  Race Condition Guard : {'✅ PASS' if race_ok else '❌ FAIL'}")
    print(f"  Idempotency Guard    : {'✅ PASS' if idem_ok else '❌ FAIL'}")
    print(f"{'═'*60}")

    r.flushdb()
    print("\n🧹  Redis DB-15 flushed (clean).")


if __name__ == '__main__':
    main()
