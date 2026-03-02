"""
FASHIONISTAR - Phase 12 Extreme Infrastructure Stress Tester
============================================================
Targets: Local Redis (127.0.0.1:6379) for both Cache and Celery broker.

Tests:
  1. Redis raw throughput via async pipelining (target: >100k ops/sec)
  2. Cache SET/GET latency under extreme concurrency (1000 concurrent tasks)
  3. Celery task dispatch / ingestion rate (queue flooding)
  4. Vector search pattern simulation (HSET/HSCAN for AI framework)

Usage:
  python stress_redis_celery.py [--ops 200000] [--concurrency 500]
"""

import asyncio
import time
import statistics
import argparse
import sys

try:
    import redis.asyncio as aioredis
except ImportError:
    print("ERROR: Install redis first:  pip install redis[asyncio] hiredis")
    sys.exit(1)

# ─── Defaults ────────────────────────────────────────────────────────────────
REDIS_URL = "redis://127.0.0.1:6379/0"
PIPELINE_BATCH = 2_000
DEFAULT_OPS = 200_000
DEFAULT_CONCURRENCY = 200
BAR = "=" * 62

# ─── Helpers ─────────────────────────────────────────────────────────────────

def _pct(data: list[float], p: int) -> float:
    if not data:
        return 0.0
    data = sorted(data)
    idx  = max(0, int(len(data) * p / 100) - 1)
    return round(data[idx], 3)

def _fmt(n: float) -> str:
    if n >= 1_000_000:
        return f"{n/1_000_000:.2f}M"
    if n >= 1_000:
        return f"{n/1_000:.1f}k"
    return str(int(n))

# ─── 1. Pipeline throughput ───────────────────────────────────────────────────

async def bench_pipeline_throughput(client: aioredis.Redis, total_ops: int) -> dict:
    print(f"\n[1] Pipeline SET Throughput  ({_fmt(total_ops)} ops, batch={_fmt(PIPELINE_BATCH)})")

    batches    = total_ops // PIPELINE_BATCH
    sent       = 0
    t_start    = time.perf_counter()

    for b in range(batches):
        async with client.pipeline(transaction=False) as pipe:
            for i in range(PIPELINE_BATCH):
                key = f"bench:pipe:{b}:{i}"
                pipe.set(key, f"v{i}", ex=30)
            await pipe.execute()
        sent += PIPELINE_BATCH

    elapsed = time.perf_counter() - t_start
    ops_sec = sent / elapsed

    print(f"    Ops sent     : {_fmt(sent)}")
    print(f"    Wall time    : {elapsed:.2f}s")
    print(f"    Throughput   : {_fmt(ops_sec)} ops/sec")
    return {"ops": sent, "elapsed": elapsed, "ops_sec": ops_sec}


# ─── 2. Concurrent GET/SET latency ───────────────────────────────────────────

async def _single_set_get(sem: asyncio.Semaphore, client: aioredis.Redis, key: str, value: str) -> float:
    async with sem:
        t0 = time.perf_counter()
        await client.set(key, value, ex=30)
        await client.get(key)
        return (time.perf_counter() - t0) * 1000  # ms

async def bench_concurrent_latency(client: aioredis.Redis, concurrency: int, total: int) -> dict:
    print(f"\n[2] Concurrent GET/SET Latency  (concurrency={concurrency}, total={_fmt(total)})")
    sem = asyncio.Semaphore(concurrency)
    tasks = [
        asyncio.create_task(_single_set_get(sem, client, f"lat:{i}", f"payload_{i}"))
        for i in range(total)
    ]
    t0 = time.perf_counter()
    latencies = await asyncio.gather(*tasks)
    elapsed   = time.perf_counter() - t0
    ops_sec   = total / elapsed

    print(f"    Ops          : {_fmt(len(latencies))}")
    print(f"    Wall time    : {elapsed:.2f}s")
    print(f"    Throughput   : {_fmt(ops_sec)} ops/sec")
    print(f"    Latency avg  : {statistics.mean(latencies):.3f}ms")
    print(f"    Latency p50  : {_pct(list(latencies), 50):.3f}ms")
    print(f"    Latency p95  : {_pct(list(latencies), 95):.3f}ms")
    print(f"    Latency p99  : {_pct(list(latencies), 99):.3f}ms")
    print(f"    Latency max  : {max(latencies):.3f}ms")
    return {"ops": len(latencies), "elapsed": elapsed, "ops_sec": ops_sec,
            "p50": _pct(list(latencies), 50), "p99": _pct(list(latencies), 99)}


# ─── 3. Celery queue flood simulation ────────────────────────────────────────
# We simulate Celery by pushing raw task blobs into a Redis list (the actual
# Celery broker queue key format). This measures queue ingestion independently
# of a running Celery worker so the bench is deterministic.

CELERY_QUEUE_KEY = "celery"   # Default queue
_FAKE_TASK_BODY  = (
    b'[[1, 2, 3], {"countdown": 0, "expires": null, "retries": 0, "task": '
    b'"fashionistar.tasks.noop", "id": "test-uuid", "args": [], "kwargs": {}},'
    b' "2.0"]'
)

async def bench_celery_queue_ingest(client: aioredis.Redis, total: int) -> dict:
    print(f"\n[3] Celery Queue Flood   ({_fmt(total)} tasks pushed)")
    t0 = time.perf_counter()
    async with client.pipeline(transaction=False) as pipe:
        for i in range(total):
            pipe.lpush(CELERY_QUEUE_KEY, _FAKE_TASK_BODY)
    # We pop the whole queue back to keep Redis clean
    await client.delete(CELERY_QUEUE_KEY)

    # Redo properly — push in smaller pipelines to measure actual perf
    batches = total // PIPELINE_BATCH
    sent    = 0
    t0      = time.perf_counter()
    for _ in range(batches):
        async with client.pipeline(transaction=False) as pipe:
            for __ in range(PIPELINE_BATCH):
                pipe.lpush(CELERY_QUEUE_KEY, _FAKE_TASK_BODY)
            await pipe.execute()
        sent += PIPELINE_BATCH

    elapsed  = time.perf_counter() - t0
    tasks_sec = sent / elapsed
    qlen     = await client.llen(CELERY_QUEUE_KEY)

    # cleanup
    await client.delete(CELERY_QUEUE_KEY)

    print(f"    Tasks pushed : {_fmt(sent)}")
    print(f"    Wall time    : {elapsed:.2f}s")
    print(f"    Queue rate   : {_fmt(tasks_sec)} tasks/sec")
    print(f"    Queue len    : {_fmt(qlen)} (before cleanup)")
    return {"tasks": sent, "elapsed": elapsed, "tasks_sec": tasks_sec}


# ─── 4. Vector search pattern (HSET / HSCAN) ─────────────────────────────────

async def bench_vector_search_pattern(client: aioredis.Redis, total: int) -> dict:
    print(f"\n[4] AI/Vector Hash Pattern   (HSET+HSCAN, {_fmt(total)} docs)")
    NS = "fashionistar:vector"
    t0 = time.perf_counter()
    async with client.pipeline(transaction=False) as pipe:
        for i in range(min(total, 10_000)):  # capped at 10k to stay fast
            pipe.hset(f"{NS}:{i}", mapping={
                "product_id": str(i),
                "embedding_dim": "512",
                "score": f"{0.9 - i * 0.00001:.6f}",
                "tags": "fashion,ai,vector"
            })
        await pipe.execute()

    # Scan to count
    count  = 0
    cursor = 0
    while True:
        cursor, keys = await client.scan(cursor=cursor, match=f"{NS}:*", count=500)
        count += len(keys)
        if cursor == 0:
            break

    elapsed    = time.perf_counter() - t0
    writes_sec = min(total, 10_000) / elapsed

    # cleanup
    keys_to_del = [f"{NS}:{i}" for i in range(min(total, 10_000))]
    if keys_to_del:
        for i in range(0, len(keys_to_del), 1000):
            await client.delete(*keys_to_del[i:i+1000])

    print(f"    Docs written : {_fmt(min(total, 10_000))}")
    print(f"    Docs scanned : {_fmt(count)}")
    print(f"    Wall time    : {elapsed:.2f}s")
    print(f"    Write rate   : {_fmt(writes_sec)} docs/sec")
    return {"docs": min(total, 10_000), "scanned": count, "elapsed": elapsed,
            "writes_sec": writes_sec}


# ─── Main ─────────────────────────────────────────────────────────────────────

async def main(total_ops: int, concurrency: int) -> None:
    print(BAR)
    print("  FASHIONISTAR  Redis + Celery Extreme Stress Test")
    print(BAR)
    print(f"  Redis URL    : {REDIS_URL}")
    print(f"  Target ops   : {_fmt(total_ops)}")
    print(f"  Concurrency  : {concurrency}")
    print(BAR)

    client = aioredis.from_url(
        REDIS_URL,
        encoding="utf-8",
        decode_responses=True,
        max_connections=1024,   # must exceed max concurrency
    )

    # Warm-up
    print("\nWarm-up ping ...", end=" ", flush=True)
    pong = await client.ping()
    print("PONG" if pong else "FAIL")
    if not pong:
        print("ERROR: Redis not reachable at", REDIS_URL)
        await client.aclose()
        sys.exit(1)

    r1 = await bench_pipeline_throughput(client, total_ops)
    r2 = await bench_concurrent_latency(client, concurrency, min(total_ops, 50_000))
    r3 = await bench_celery_queue_ingest(client, min(total_ops, 200_000))
    r4 = await bench_vector_search_pattern(client, total_ops)

    await client.aclose()

    # ── Summary ──────────────────────────────────────────────────
    print(f"\n{BAR}")
    print("  SUMMARY")
    print(BAR)
    print(f"  Pipeline throughput      : {_fmt(r1['ops_sec'])} ops/sec")
    print(f"  Concurrent GET/SET rate  : {_fmt(r2['ops_sec'])} ops/sec")
    print(f"  GET/SET p50 latency      : {r2['p50']}ms")
    print(f"  GET/SET p99 latency      : {r2['p99']}ms")
    print(f"  Celery queue flood rate  : {_fmt(r3['tasks_sec'])} tasks/sec")
    print(f"  Vector hash write rate   : {_fmt(r4['writes_sec'])} docs/sec")

    goal = 100_000
    status = "PASS" if r1["ops_sec"] >= goal else "NOTE (add --ops flag & hiredis for higher)"
    print(f"\n  100k ops/sec goal        : {_fmt(goal)}")
    print(f"  Pipeline result          : {_fmt(r1['ops_sec'])} ops/sec  [{status}]")
    print(BAR)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Fashionistar Redis Stress Test")
    parser.add_argument("--ops",         type=int, default=DEFAULT_OPS,
                        help=f"Total operations (default: {DEFAULT_OPS})")
    parser.add_argument("--concurrency", type=int, default=DEFAULT_CONCURRENCY,
                        help=f"Concurrent tasks for latency bench (default: {DEFAULT_CONCURRENCY})")
    args = parser.parse_args()
    asyncio.run(main(args.ops, args.concurrency))
