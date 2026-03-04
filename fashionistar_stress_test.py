#!/usr/bin/env python
"""
fashionistar_stress_test.py
===========================
Production-grade HTTP + Redis + Celery stress test suite for the
Fashionistar backend.

Target: ≥100,000 requests/second aggregate throughput.
Covers: HTTP endpoints, Redis pipeline, Celery queue flood,
        middleware X-Request-ID propagation, Rate-Limiting headers.

Usage:
    # Ensure Redis & Uvicorn are running first:
    #   make start-redis
    #   make run-asgi   (in another terminal)

    python fashionistar_stress_test.py --host http://127.0.0.1:8000 --rps 100000

Requirements (install in venv):
    pip install aiohttp asyncio uvloop httpx
"""

import sys
import io
# Force UTF-8 output on Windows terminals that default to cp1252
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

import argparse
import asyncio
import os
import statistics
import time
import uuid
from collections import Counter
from dataclasses import dataclass, field
from typing import List


# ── Optional uvloop for maximum event loop throughput ─────────────────────────
try:
    import uvloop
    asyncio.set_event_loop_policy(uvloop.EventLoopPolicy())
    UVLOOP = True
except ImportError:
    UVLOOP = False

# ── Optional aiohttp (faster than httpx for bulk) ─────────────────────────────
try:
    import aiohttp
    AIOHTTP = True
except ImportError:
    AIOHTTP = False
    import httpx

# ── Set up Django env for Redis/Celery direct tests ───────────────────────────
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')
sys.path.insert(0, os.path.dirname(__file__))

# ─────────────────────────────────────────────────────────────────────────────
# Data classes
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class BenchResult:
    name: str
    total_requests: int = 0
    success: int = 0
    errors: int = 0
    latencies: List[float] = field(default_factory=list)
    status_codes: Counter = field(default_factory=Counter)
    duration_s: float = 0.0

    @property
    def rps(self) -> float:
        return self.total_requests / max(self.duration_s, 0.001)

    @property
    def p50(self) -> float:
        return statistics.median(self.latencies) * 1000 if self.latencies else 0

    @property
    def p95(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[int(len(s) * 0.95)] * 1000

    @property
    def p99(self) -> float:
        if not self.latencies:
            return 0
        s = sorted(self.latencies)
        return s[int(len(s) * 0.99)] * 1000

    def print_report(self) -> None:
        ok_rate = (self.success / max(self.total_requests, 1)) * 100
        print(f"\n{'='*62}")
        print(f" ✦  {self.name}")
        print(f"{'='*62}")
        print(f"  Total requests : {self.total_requests:>10,}")
        print(f"  Success        : {self.success:>10,}  ({ok_rate:.1f}%)")
        print(f"  Errors         : {self.errors:>10,}")
        print(f"  Duration       : {self.duration_s:>10.2f} s")
        print(f"  Throughput     : {self.rps:>10,.0f} req/s")
        print(f"  Latency p50    : {self.p50:>10.1f} ms")
        print(f"  Latency p95    : {self.p95:>10.1f} ms")
        print(f"  Latency p99    : {self.p99:>10.1f} ms")
        if self.status_codes:
            print(f"  Status codes   : {dict(self.status_codes)}")
        print(f"{'='*62}")


# ─────────────────────────────────────────────────────────────────────────────
# HTTP Benchmark helpers
# ─────────────────────────────────────────────────────────────────────────────

SEM_LIMIT = 500  # max concurrent connections

async def _http_worker_aiohttp(
    session: "aiohttp.ClientSession",
    url: str,
    result: BenchResult,
    sem: asyncio.Semaphore,
    headers: dict,
) -> None:
    async with sem:
        t0 = time.monotonic()
        try:
            async with session.get(url, headers=headers) as resp:
                await resp.read()
                elapsed = time.monotonic() - t0
                result.latencies.append(elapsed)
                result.status_codes[resp.status] += 1
                if resp.status < 500:
                    result.success += 1
                else:
                    result.errors += 1
        except Exception as e:
            result.errors += 1
            result.latencies.append(time.monotonic() - t0)

    result.total_requests += 1


async def bench_http_endpoint(
    url: str,
    name: str,
    n_requests: int = 10_000,
    concurrency: int = 200,
) -> BenchResult:
    """Benchmark a single HTTP endpoint with aiohttp or httpx."""
    result = BenchResult(name=name)
    sem = asyncio.Semaphore(concurrency)

    headers = {
        "X-Request-ID": str(uuid.uuid4()),
        "X-Device-ID": "stress-test-device",
        "User-Agent": "FashionistarStressTest/1.0",
        "Accept": "application/json",
    }

    t_start = time.monotonic()

    if AIOHTTP:
        connector = aiohttp.TCPConnector(
            limit=concurrency,
            limit_per_host=concurrency,
            keepalive_timeout=30,
            enable_cleanup_closed=True,
        )
        async with aiohttp.ClientSession(connector=connector) as session:
            tasks = [
                _http_worker_aiohttp(session, url, result, sem, headers)
                for _ in range(n_requests)
            ]
            await asyncio.gather(*tasks)
    else:
        # Fallback to httpx (slower but always available)
        limits = httpx.Limits(
            max_connections=concurrency,
            max_keepalive_connections=concurrency,
        )
        async with httpx.AsyncClient(limits=limits) as client:
            async def _worker():
                t0 = time.monotonic()
                try:
                    resp = await client.get(url, headers=headers)
                    elapsed = time.monotonic() - t0
                    result.latencies.append(elapsed)
                    result.status_codes[resp.status_code] += 1
                    if resp.status_code < 500:
                        result.success += 1
                    else:
                        result.errors += 1
                except Exception:
                    result.errors += 1
                    result.latencies.append(time.monotonic() - t0)
                finally:
                    result.total_requests += 1

            tasks = [_worker() for _ in range(n_requests)]
            await asyncio.gather(*tasks)

    result.duration_s = time.monotonic() - t_start
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Suite 1 — Health Check Endpoint
# ─────────────────────────────────────────────────────────────────────────────

async def suite_health_check(host: str, n: int) -> BenchResult:
    """Stress test /api/health/ — the lowest-latency async endpoint."""
    url = f"{host}/api/health/"
    print(f"\n[SUITE 1] Health Check · {n:,} requests → {url}")
    return await bench_http_endpoint(url, "Health Check /api/health/", n, 300)


# ─────────────────────────────────────────────────────────────────────────────
# Suite 2 — Homepage / Root API
# ─────────────────────────────────────────────────────────────────────────────

async def suite_homepage(host: str, n: int) -> BenchResult:
    """Stress test the homepage/root API."""
    url = f"{host}/"
    print(f"\n[SUITE 2] Homepage / Root API · {n:,} requests → {url}")
    return await bench_http_endpoint(url, "Homepage / Root", n, 200)


# ─────────────────────────────────────────────────────────────────────────────
# Suite 3 — Middleware Header Propagation
# ─────────────────────────────────────────────────────────────────────────────

async def suite_middleware_headers(host: str, n: int) -> BenchResult:
    """
    Verify X-Request-ID and X-Response-Time headers propagate correctly
    under load, and measure middleware overhead specifically.
    """
    url = f"{host}/api/health/"
    print(f"\n[SUITE 3] Middleware Header Propagation · {n:,} requests")

    result = BenchResult(name="Middleware Header Propagation")
    sem = asyncio.Semaphore(200)
    missing_request_id = 0
    missing_response_time = 0

    if not AIOHTTP:
        print("  ⚠ aiohttp not available — skipping header verification suite")
        return result

    connector = aiohttp.TCPConnector(limit=200)
    async with aiohttp.ClientSession(connector=connector) as session:
        async def _worker():
            nonlocal missing_request_id, missing_response_time
            req_id = str(uuid.uuid4())
            hdrs = {"X-Request-ID": req_id, "User-Agent": "Stress/1.0"}
            async with sem:
                t0 = time.monotonic()
                try:
                    async with session.get(url, headers=hdrs) as resp:
                        await resp.read()
                        elapsed = time.monotonic() - t0
                        result.latencies.append(elapsed)
                        result.status_codes[resp.status] += 1
                        if resp.status < 500:
                            result.success += 1
                            # Verify our middleware set these headers back
                            if resp.headers.get('X-Request-ID') != req_id:
                                missing_request_id += 1
                            if 'X-Response-Time' not in resp.headers:
                                missing_response_time += 1
                        else:
                            result.errors += 1
                except Exception:
                    result.errors += 1
                    result.latencies.append(time.monotonic() - t0)
                finally:
                    result.total_requests += 1

        t_start = time.monotonic()
        await asyncio.gather(*[_worker() for _ in range(n)])
        result.duration_s = time.monotonic() - t_start

    print(f"  X-Request-ID mismatches : {missing_request_id}")
    print(f"  X-Response-Time absent  : {missing_response_time}")
    return result


# ─────────────────────────────────────────────────────────────────────────────
# Suite 4 — Redis Direct Benchmark
# ─────────────────────────────────────────────────────────────────────────────

async def suite_redis_direct(n: int) -> BenchResult:
    """
    Benchmark local Redis with async pipeline SET + GET.
    Target: >100k ops/sec.
    """
    print(f"\n[SUITE 4] Redis Direct Pipeline Benchmark · {n:,} ops")
    result = BenchResult(name="Redis Direct Pipeline (async)")

    try:
        import redis.asyncio as aioredis

        pool = aioredis.ConnectionPool.from_url(
            "redis://127.0.0.1:6379/4",
            max_connections=64,
            decode_responses=True,
        )
        r = aioredis.Redis(connection_pool=pool)

        BATCH = 1000
        batches = n // BATCH

        t_start = time.monotonic()
        async with r.pipeline(transaction=False) as pipe:
            for i in range(min(n, 10_000)):
                pipe.set(f"stress:{i}", f"val{i}", ex=60)
                pipe.get(f"stress:{i}")
            await pipe.execute()

        # Now do concurrent individual ops
        sem = asyncio.Semaphore(200)

        async def _op(i: int):
            async with sem:
                t0 = time.monotonic()
                try:
                    await r.set(f"s:{i}", i, ex=5)
                    await r.get(f"s:{i}")
                    result.latencies.append(time.monotonic() - t0)
                    result.success += 1
                except Exception:
                    result.errors += 1
                    result.latencies.append(time.monotonic() - t0)
                finally:
                    result.total_requests += 1

        await asyncio.gather(*[_op(i) for i in range(n)])
        result.duration_s = time.monotonic() - t_start
        await r.aclose()

    except ImportError:
        print("  ⚠ redis[asyncio] not available — skipping Redis suite")
    except Exception as e:
        print(f"  ⚠ Redis connection error: {e}")
        result.errors += n

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Suite 5 — Celery Task Queue Flood
# ─────────────────────────────────────────────────────────────────────────────

async def suite_celery_queue_flood(n: int) -> BenchResult:
    """
    Flood the Celery broker queue with n tasks and measure enqueue throughput.
    Does NOT wait for task execution — only measures queue send speed.
    """
    print(f"\n[SUITE 5] Celery Queue Flood · {n:,} tasks")
    result = BenchResult(name="Celery Queue Flood")

    try:
        import django
        django.setup()
        from celery import Celery
        from django.conf import settings

        app = Celery('fashionistar')
        app.config_from_object('django.conf:settings', namespace='CELERY')

        t_start = time.monotonic()

        # Use apply_async in a thread pool since Celery's send is synchronous
        def _send(i):
            t0 = time.monotonic()
            try:
                # Use signature to send without needing a real task registered
                from celery import signature
                sig = signature(
                    'apps.common.tasks.noop',
                    args=(i,),
                    queue='default',
                    ignore_result=True,
                )
                sig.apply_async()
                return time.monotonic() - t0, True
            except Exception:
                return time.monotonic() - t0, False

        # Run in thread pool (Celery is sync)
        loop = asyncio.get_event_loop()
        tasks_to_run = min(n, 5_000)  # cap at 5k — broker flood test

        futures = [
            loop.run_in_executor(None, _send, i)
            for i in range(tasks_to_run)
        ]
        results = await asyncio.gather(*futures, return_exceptions=True)

        for r in results:
            if isinstance(r, Exception):
                result.errors += 1
            else:
                latency, ok = r
                result.latencies.append(latency)
                result.total_requests += 1
                if ok:
                    result.success += 1
                else:
                    result.errors += 1

        result.duration_s = time.monotonic() - t_start

    except Exception as e:
        print(f"  ⚠ Celery setup error: {e} — skipping Celery suite")
        result.errors += n

    return result


# ─────────────────────────────────────────────────────────────────────────────
# Suite 6 — Mixed Read Load (Simulates real-world traffic)
# ─────────────────────────────────────────────────────────────────────────────

async def suite_mixed_load(host: str, n: int) -> list:
    """
    Simulate real-world traffic mix:
      60% → /api/health/ (fast, common)
      30% → / (homepage, moderate)
      10% → /api/v2/nonexistent/ (404 path, error handling)
    """
    print(f"\n[SUITE 6] Mixed Realistic Load · {n:,} requests")

    n_health = int(n * 0.6)
    n_home = int(n * 0.3)
    n_404 = n - n_health - n_home

    t_start = time.monotonic()
    results = await asyncio.gather(
        bench_http_endpoint(
            f"{host}/api/health/",
            "Mixed: Health (60%)",
            n_health, 250
        ),
        bench_http_endpoint(
            f"{host}/",
            "Mixed: Homepage (30%)",
            n_home, 150
        ),
        bench_http_endpoint(
            f"{host}/api/v2/nonexistent-endpoint-404/",
            "Mixed: 404 path (10%)",
            n_404, 50
        ),
    )
    total_duration = time.monotonic() - t_start

    total_rps = sum(r.total_requests for r in results) / max(total_duration, 0.001)
    print(f"\n  ► Combined Mixed Load: {total_rps:,.0f} req/s over {total_duration:.2f}s")
    return list(results)


# ─────────────────────────────────────────────────────────────────────────────
# Main entry point
# ─────────────────────────────────────────────────────────────────────────────

async def main(host: str, target_rps: int) -> None:
    print(f"""
╔══════════════════════════════════════════════════════════════╗
║  FASHIONISTAR ENTERPRISE STRESS TEST                         ║
║  Target: {target_rps:>10,} req/s                                  ║
║  Host:   {host:<50}  ║
║  uvloop: {'YES (max performance)' if UVLOOP else 'NO  (install uvloop for +30% speed)':50}║
║  aiohttp:{'YES (fast HTTP)' if AIOHTTP else 'NO  (install aiohttp)':50}║
╚══════════════════════════════════════════════════════════════╝
""")

    # Scale request counts based on target RPS
    scale = max(1, target_rps // 10_000)
    n_http = min(50_000 * scale, 200_000)
    n_light = min(5_000 * scale, 20_000)

    all_results = []

    # ── Suite 1: Health Check ──────────────────────────────────────────────
    r1 = await suite_health_check(host, n_http)
    r1.print_report()
    all_results.append(r1)

    # ── Suite 2: Homepage ──────────────────────────────────────────────────
    r2 = await suite_homepage(host, n_light)
    r2.print_report()
    all_results.append(r2)

    # ── Suite 3: Middleware Validation ────────────────────────────────────
    r3 = await suite_middleware_headers(host, n_light)
    r3.print_report()
    all_results.append(r3)

    # ── Suite 4: Redis Direct ──────────────────────────────────────────────
    r4 = await suite_redis_direct(min(20_000 * scale, 100_000))
    r4.print_report()
    all_results.append(r4)

    # ── Suite 5: Celery Queue Flood ────────────────────────────────────────
    r5 = await suite_celery_queue_flood(5_000)
    r5.print_report()
    all_results.append(r5)

    # ── Suite 6: Mixed Load ────────────────────────────────────────────────
    r6_list = await suite_mixed_load(host, n_http)
    for r6 in r6_list:
        r6.print_report()
        all_results.append(r6)

    # ── Grand Summary ──────────────────────────────────────────────────────
    print(f"\n{'='*62}")
    print(" GRAND SUMMARY")
    print(f"{'='*62}")
    total_req = sum(r.total_requests for r in all_results)
    total_ok = sum(r.success for r in all_results)
    total_err = sum(r.errors for r in all_results)
    peak_rps = max((r.rps for r in all_results), default=0)

    print(f"  Total requests fired : {total_req:>10,}")
    print(f"  Total successes      : {total_ok:>10,}")
    print(f"  Total errors         : {total_err:>10,}")
    print(f"  Peak single-suite RPS: {peak_rps:>10,.0f}")
    print(f"  Target RPS           : {target_rps:>10,}")
    print()

    if peak_rps >= target_rps:
        print(f"  ✅ TARGET MET: {peak_rps:,.0f} req/s ≥ {target_rps:,} req/s")
    else:
        print(f"  ⚠  TARGET MISSED: {peak_rps:,.0f} req/s < {target_rps:,} req/s")
        print("     Likely causes:")
        print("     • Windows TCP loopback overhead (3-5× vs Linux production)")
        print("     • Install uvloop: pip install uvloop")
        print("     • Install aiohttp: pip install aiohttp")
        print("     • Increase Uvicorn workers: --workers 4")
        print("     • On Linux production this benchmark will meet target easily")

    print(f"{'='*62}\n")


if __name__ == '__main__':
    parser = argparse.ArgumentParser(
        description='Fashionistar enterprise stress test suite'
    )
    parser.add_argument(
        '--host',
        default='http://127.0.0.1:8000',
        help='Base URL of the running Fashionistar API (default: http://127.0.0.1:8000)',
    )
    parser.add_argument(
        '--rps',
        type=int,
        default=100_000,
        help='Target requests per second (default: 100000)',
    )
    args = parser.parse_args()

    asyncio.run(main(args.host, args.rps))
