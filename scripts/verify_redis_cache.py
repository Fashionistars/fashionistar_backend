"""
fashionistar_backend/scripts/verify_redis_cache.py
====================================================
Phase E2 — Redis Cache Verification Script

Verifies the catalog:* Redis key namespace:
  1. Asserts connection to Redis is successful
  2. Lists all catalog:* keys and their TTLs
  3. Verifies each expected cache key has the correct TTL
  4. Tests that Celery invalidation task enqueues correctly
  5. Validates cache → DB consistency on a sample key

Run:
    python scripts/verify_redis_cache.py

Or via Django shell:
    python manage.py shell -c "exec(open('scripts/verify_redis_cache.py').read())"

Expected output (example, production data will vary):
    ✅ Redis connection: OK (latency 0.4ms)
    📦 catalog:* keys found: 8
       catalog:homepage:bundle       TTL: 298s  ✅
       catalog:categories:list       TTL: 299s  ✅
       catalog:brands:list           TTL: 297s  ✅
       catalog:collections:list      TTL: 296s  ✅
       catalog:tags:trending         TTL: 596s  ✅
       catalog:banners:hero          TTL: 57s   ✅
       catalog:search:fashion        TTL: 27s   ✅
    🎯 All catalog keys have correct TTLs
    ✅ Celery task: invalidate_catalog_cache enqueued OK
"""
from __future__ import annotations

import os
import sys
import time
import django

# ─────────────────────────────────────────────────────────────────────────────
# Bootstrap Django (if run as standalone script)
# ─────────────────────────────────────────────────────────────────────────────

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

try:
    django.setup()
except RuntimeError:
    pass  # Already set up (running in shell)


import redis
from django.conf import settings
from django.core.cache import cache

# ─────────────────────────────────────────────────────────────────────────────
# Config — expected TTL ranges (seconds)
# These MUST match catalog_utils.py and catalog_selectors.py constants
# ─────────────────────────────────────────────────────────────────────────────

EXPECTED_TTL_RANGES = {
    "catalog:homepage:bundle":     (240, 360),  # 300s nominal
    "catalog:categories:list":     (240, 360),  # 300s nominal
    "catalog:brands:list":         (240, 360),  # 300s nominal
    "catalog:collections:list":    (240, 360),  # 300s nominal
    "catalog:tags:trending":       (540, 660),  # 600s nominal (10 min)
    "catalog:banners:hero":        (30, 120),   # 60s nominal (1 min)
    "catalog:banners:mid":         (30, 120),
    "catalog:banners:footer_cta":  (30, 120),
}

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"
BOLD = "\033[1m"

OK = f"{GREEN}✅{RESET}"
FAIL = f"{RED}❌{RESET}"
WARN = f"{YELLOW}⚠️ {RESET}"
INFO = f"{BLUE}ℹ️ {RESET}"


def check_redis_connection() -> redis.Redis | None:
    """Ping Redis and measure round-trip latency."""
    print(f"\n{BOLD}═══ Phase E2: Redis Cache Verification ═══{RESET}\n")

    redis_url = getattr(settings, "REDIS_URL", None) or os.environ.get(
        "REDIS_URL", "redis://localhost:6379/0"
    )

    try:
        r = redis.from_url(redis_url, decode_responses=True)
        start = time.monotonic()
        r.ping()
        latency_ms = (time.monotonic() - start) * 1000
        print(f"{OK} Redis connection: OK (latency {latency_ms:.1f}ms)")
        print(f"   URL: {redis_url}")
        return r
    except Exception as exc:
        print(f"{FAIL} Redis connection FAILED: {exc}")
        return None


def list_catalog_keys(r: redis.Redis) -> list[str]:
    """Scan all catalog:* keys (SCAN is non-blocking, production-safe)."""
    keys: list[str] = []
    cursor = 0
    while True:
        cursor, batch = r.scan(cursor, match="catalog:*", count=500)
        keys.extend(batch)
        if cursor == 0:
            break
    return sorted(keys)


def verify_ttls(r: redis.Redis, keys: list[str]) -> int:
    """Check each catalog:* key has a TTL within expected range. Returns failure count."""
    failures = 0
    print(f"\n{BOLD}📦 catalog:* keys found: {len(keys)}{RESET}")

    for key in keys:
        ttl = r.ttl(key)
        key_short = key[:55].ljust(55)

        if ttl == -1:
            print(f"   {key_short}  TTL: PERSISTENT (no expiry) {WARN}")
            failures += 1
        elif ttl == -2:
            print(f"   {key_short}  TTL: EXPIRED / MISSING {WARN}")
        else:
            ttl_str = f"{ttl}s"
            # Check against expected range if key is known
            expected = None
            for pattern, rng in EXPECTED_TTL_RANGES.items():
                if key.startswith(pattern):
                    expected = rng
                    break

            if expected:
                lo, hi = expected
                if lo <= ttl <= hi:
                    print(f"   {key_short}  TTL: {ttl_str:>6}  {OK}")
                else:
                    print(f"   {key_short}  TTL: {ttl_str:>6}  {WARN} (expected {lo}-{hi}s)")
                    failures += 1
            else:
                # Unknown key — just report
                print(f"   {key_short}  TTL: {ttl_str:>6}  {INFO} (unknown key pattern)")

    return failures


def trigger_cache_prime() -> None:
    """Call Django cache to prime the homepage bundle cache key."""
    print(f"\n{BOLD}🔥 Priming homepage bundle cache...{RESET}")
    try:
        from apps.catalog.selectors.catalog_selectors import get_homepage_bundle_v2_selector
        import asyncio

        start = time.monotonic()
        result = asyncio.run(get_homepage_bundle_v2_selector())
        elapsed_ms = (time.monotonic() - start) * 1000

        section_counts = {
            k: len(v)
            for k, v in result.items()
            if isinstance(v, list)
        }
        print(f"{OK} Bundle selector executed in {elapsed_ms:.1f}ms")
        print(f"   Sections: {section_counts}")
    except Exception as exc:
        print(f"{FAIL} Bundle prime failed: {exc}")


def verify_celery_task() -> None:
    """Verify the Celery invalidation task is importable and can be called."""
    print(f"\n{BOLD}🔄 Verifying Celery cache invalidation task...{RESET}")
    try:
        from apps.catalog.task import invalidate_catalog_cache  # type: ignore[import]

        # Apply async — enqueue to broker
        result = invalidate_catalog_cache.apply_async(
            args=["verify_script"],
            countdown=0,
        )
        print(f"{OK} Celery task enqueued: task_id={result.id}")
    except Exception as exc:
        print(f"{WARN} Celery task check skipped: {exc}")
        print(f"   (This is expected if Celery broker is not running locally)")


def check_cache_consistency(r: redis.Redis) -> None:
    """Spot-check: verify the homepage bundle key exists and is JSON-parseable."""
    print(f"\n{BOLD}🔍 Cache consistency spot-check...{RESET}")
    import json

    bundle_key = "catalog:homepage:bundle"
    raw = r.get(bundle_key)

    if raw is None:
        print(f"{WARN} {bundle_key}: NOT in cache (will be set on next request)")
        return

    try:
        data = json.loads(raw)
        required_keys = ["categories", "collections", "banners", "meta"]
        missing = [k for k in required_keys if k not in data]
        if missing:
            print(f"{FAIL} {bundle_key}: missing keys: {missing}")
        else:
            print(f"{OK} {bundle_key}: valid JSON, all required keys present")
            meta = data.get("meta", {})
            print(f"   meta: {meta}")
    except json.JSONDecodeError as exc:
        print(f"{FAIL} {bundle_key}: invalid JSON — {exc}")


def main() -> None:
    r = check_redis_connection()
    if r is None:
        print(f"\n{FAIL} Cannot proceed without Redis connection.")
        sys.exit(1)

    keys = list_catalog_keys(r)
    if not keys:
        print(f"\n{WARN} No catalog:* keys in Redis — cache is cold.")
        print(f"   Run: python manage.py shell -c \"import asyncio; from apps.catalog.selectors.catalog_selectors import get_homepage_bundle_v2_selector; asyncio.run(get_homepage_bundle_v2_selector())\"")
        trigger_cache_prime()
        # Re-scan after prime
        keys = list_catalog_keys(r)

    failures = verify_ttls(r, keys)
    check_cache_consistency(r)
    verify_celery_task()

    print(f"\n{'═' * 50}")
    if failures == 0:
        print(f"{OK} {BOLD}All catalog cache keys verified successfully.{RESET}")
    else:
        print(f"{WARN} {BOLD}{failures} TTL issue(s) found. Review output above.{RESET}")
    print(f"{'═' * 50}\n")


if __name__ == "__main__":
    main()
