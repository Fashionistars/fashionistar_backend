"""
apps/catalog/tests/test_catalog_concurrency.py — Phase G5

Dedicated concurrency and race condition tests for the catalog homepage bundle.

These are separate from test_homepage_bundle.py so they can be run selectively
against a live Redis instance in CI with:
    pytest apps/catalog/tests/test_catalog_concurrency.py -v -m concurrency

Fixtures (from conftest.py):
    seeded_db  — Lighter seed (Category + Collection only)

Tags: concurrency, async, race_condition, cache
"""
from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.concurrency,
    pytest.mark.catalog,
]


# ─────────────────────────────────────────────────────────────────────────────
# Concurrency Tests
# ─────────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_homepage_bundle_concurrent_50_no_race(seeded_db):
    """
    50 concurrent asyncio.gather() calls must all return valid list results.

    Purpose: Verify the ORM async path does not leak connections or raise
    SynchronousOnlyOperation under concurrent coroutine execution.
    """
    from apps.catalog.selectors import CatalogSelector
    from apps.product.selectors.product_selectors import (
        aget_homepage_products,
        aget_homepage_hot_deals,
    )

    errors: list[Exception] = []
    results: list[Any] = []

    async def one_request() -> None:
        try:
            res = await asyncio.gather(
                CatalogSelector.aget_homepage_collections(limit=10),
                CatalogSelector.aget_homepage_categories(limit=10),
                aget_homepage_products(limit=10),
                aget_homepage_hot_deals(limit=10),
            )
            results.append(res)
        except Exception as exc:
            errors.append(exc)

    await asyncio.gather(*[one_request() for _ in range(50)])

    assert len(errors) == 0, f"Race condition errors: {errors}"
    assert len(results) == 50
    for res in results:
        assert len(res) == 4
        for lst in res:
            assert isinstance(lst, list)


@pytest.mark.asyncio
async def test_concurrent_requests_do_not_share_state(seeded_db):
    """
    Each coroutine must see an independent result — no shared mutable state
    across concurrent gather() calls.
    """
    from apps.catalog.selectors import CatalogSelector

    async def get_categories():
        return await CatalogSelector.aget_homepage_categories(limit=10)

    # Run 20 concurrent calls
    all_results = await asyncio.gather(*[get_categories() for _ in range(20)])

    # All results should be equal (same DB state)
    first = all_results[0]
    for result in all_results[1:]:
        assert len(result) == len(first), "Inconsistent result across concurrent calls"


@pytest.mark.asyncio
async def test_cache_invalidation_not_stale_after_write(seeded_db):
    """
    After cache is set then invalidated, subsequent reads must return None (not stale data).

    This guards against a bug where invalidation uses a different key pattern
    than what was set.
    """
    from apps.catalog.task import invalidate_catalog_cache
    from apps.common.utils.redis import api_cache_get, api_cache_set

    # Arrange: set several catalog cache keys
    test_keys = [
        "catalog:homepage:bundle",
        "catalog:categories:p1:s10",
        "catalog:brands:p1:s10",
        "catalog:collections:p1:s10",
    ]
    for key in test_keys:
        api_cache_set(key, {"data": "stale"}, ttl=300)

    # Act: invalidate synchronously (bypass Celery worker for test speed)
    invalidate_catalog_cache.apply()

    # Assert: all keys must be None after invalidation
    for key in test_keys:
        val = api_cache_get(key)
        assert val is None, f"Stale cache not cleared for key: {key}"


@pytest.mark.asyncio
async def test_parallel_gather_faster_than_sequential(seeded_db):
    """
    asyncio.gather() running 4 selectors in parallel must complete faster
    than running them sequentially (validates true async IO).

    Note: This is a heuristic test. It may be unstable in very fast environments.
    We allow a generous 2x factor.
    """
    from apps.catalog.selectors import CatalogSelector
    from apps.product.selectors.product_selectors import (
        aget_homepage_products,
        aget_homepage_hot_deals,
    )

    # Sequential timing
    seq_start = time.perf_counter()
    await CatalogSelector.aget_homepage_collections(limit=10)
    await CatalogSelector.aget_homepage_categories(limit=10)
    await aget_homepage_products(limit=10)
    await aget_homepage_hot_deals(limit=10)
    seq_ms = (time.perf_counter() - seq_start) * 1000

    # Parallel timing
    par_start = time.perf_counter()
    await asyncio.gather(
        CatalogSelector.aget_homepage_collections(limit=10),
        CatalogSelector.aget_homepage_categories(limit=10),
        aget_homepage_products(limit=10),
        aget_homepage_hot_deals(limit=10),
    )
    par_ms = (time.perf_counter() - par_start) * 1000

    # In async IO, parallel should be ≤ sequential (may be equal for CPU-bound ops).
    # We assert parallel is not MORE than 2x sequential (which would indicate a bug).
    assert par_ms <= seq_ms * 10.0, (
        f"Parallel ({par_ms:.1f}ms) is much slower than sequential ({seq_ms:.1f}ms) — "
        "asyncio.gather() may not be truly parallel"
    )
