"""
stress_health.py
Async stress tester for GET /api/health/

Usage:
    python stress_health.py [--url URL] [--concurrency N] [--requests N]

Requires: httpx  (pip install httpx)
"""
from __future__ import annotations

import argparse
import asyncio
import statistics
import time
from collections import Counter
from typing import Any

import httpx

# -- Defaults ------------------------------------------------------------------
DEFAULT_URL         = "http://127.0.0.1:8001/api/health/"
DEFAULT_CONCURRENCY = 20
DEFAULT_REQUESTS    = 100
REQUEST_TIMEOUT     = 45.0   # long: remote Redis DNS can take ~15 s on Windows

SEP  = "=" * 60
DASH = "-" * 60


# -- Core fetcher --------------------------------------------------------------

async def _fetch(
    client: httpx.AsyncClient, url: str
) -> tuple[int | Exception, float]:
    t0 = time.monotonic()
    try:
        r = await client.get(url, timeout=REQUEST_TIMEOUT)
        return r.status_code, time.monotonic() - t0
    except Exception as exc:
        return exc, time.monotonic() - t0


async def _worker(
    sem: asyncio.Semaphore,
    client: httpx.AsyncClient,
    url: str,
    results: list[tuple[Any, float]],
) -> None:
    async with sem:
        results.append(await _fetch(client, url))


# -- Main ----------------------------------------------------------------------

async def main(url: str, concurrency: int, total: int) -> None:
    print(SEP)
    print("  FASHIONISTAR  /health/  Async Stress Tester")
    print(SEP)
    print(f"  URL           : {url}")
    print(f"  Concurrency   : {concurrency}")
    print(f"  Total requests: {total}")
    print(DASH)

    # 1. Warm-up probe
    print("Warm-up probe ... ", end="", flush=True)
    async with httpx.AsyncClient() as probe:
        try:
            r = await probe.get(url, timeout=REQUEST_TIMEOUT)
            print(f"HTTP {r.status_code}  OK")
        except Exception as exc:
            print(f"FAILED  ({exc!r})")
            print("Ensure the ASGI server is running on the target port.")
            return

    # 2. Fire load
    results: list[tuple[Any, float]] = []
    sem    = asyncio.Semaphore(concurrency)
    limits = httpx.Limits(
        max_connections=concurrency,
        max_keepalive_connections=concurrency,
    )
    print(f"Firing {total} requests at concurrency={concurrency} ...", flush=True)
    t_start = time.monotonic()
    async with httpx.AsyncClient(limits=limits) as client:
        await asyncio.gather(
            *[asyncio.create_task(_worker(sem, client, url, results))
              for _ in range(total)]
        )
    elapsed = time.monotonic() - t_start

    # 3. Report
    ok_lats  = [lat for status, lat in results if isinstance(status, int)]
    errors   = [(s, l) for s, l in results if not isinstance(s, int)]
    codes    = Counter(s for s, _ in results if isinstance(s, int))

    print()
    print(DASH)
    print("  RESULTS")
    print(DASH)
    print(f"  Total requests  : {total}")
    print(f"  Concurrency     : {concurrency}")
    print(f"  Wall clock      : {elapsed:.2f} s")
    print(f"  Throughput      : {len(ok_lats)/elapsed:.2f} req/s  "
          f"(of {total} sent)")
    print()

    if ok_lats:
        ms = sorted(l * 1000 for l in ok_lats)
        p95 = ms[max(0, int(len(ms) * 0.95) - 1)]
        print(f"  Latency  avg    : {statistics.mean(ms):.1f} ms")
        print(f"           median : {statistics.median(ms):.1f} ms")
        print(f"           p95    : {p95:.1f} ms")
        print(f"           min    : {ms[0]:.1f} ms")
        print(f"           max    : {ms[-1]:.1f} ms")
    else:
        print("  No successful responses recorded.")

    print()
    print(f"  HTTP status codes  : {dict(codes)}")
    print(f"  Client-side errors : {len(errors)}")
    if errors:
        samples = {repr(e) for e, _ in errors[:5]}
        print(f"  Sample errors      : {samples}")

    print(SEP)
    overall = "PASS" if not errors else "DEGRADED (some client errors)"
    print(f"  Result : {overall}")
    print(SEP)


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="Async health-check stress tester")
    p.add_argument("--url",         default=DEFAULT_URL)
    p.add_argument("--concurrency", default=DEFAULT_CONCURRENCY, type=int)
    p.add_argument("--requests",    default=DEFAULT_REQUESTS,    type=int)
    args = p.parse_args()

    asyncio.run(main(args.url, args.concurrency, args.requests))
