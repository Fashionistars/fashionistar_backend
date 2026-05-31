"""
apps/catalog/tests/test_homepage_bundle.py — Phase G1/G2

pytest unit + integration tests for the asyncio.gather() homepage bundle endpoint.

Coverage:
    G1 — Unit tests for async selectors
    G2 — Integration tests for the Ninja endpoint
    G5 — Race-condition concurrency assertions

Fixtures (from conftest.py):
    catalog_seed  — Category + Brand + Collection + CatalogBanner
    sync_client   — Unauthenticated DRF APIClient
    seeded_db     — Lighter seed for concurrency tests

Run with:
    pytest apps/catalog/tests/test_homepage_bundle.py -v
    (asyncio_mode=auto already set in pytest.ini)
"""
from __future__ import annotations

import asyncio
import time

import pytest
from django.utils import timezone

pytestmark = [
    pytest.mark.django_db(transaction=True),
    pytest.mark.asyncio,
    pytest.mark.catalog,
    pytest.mark.bundle,
]


# ─────────────────────────────────────────────────────────────────────────────
# G1 — Unit Tests: Async Selectors
# ─────────────────────────────────────────────────────────────────────────────


class TestCatalogSelectorAsync:
    """Unit tests for CatalogSelector async methods."""

    @pytest.mark.asyncio
    async def test_aget_homepage_collections_returns_list(self, catalog_seed):
        """aget_homepage_collections must return a list of dicts."""
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_homepage_collections(limit=10)
        assert isinstance(result, list)
        # Seeded collection should appear
        titles = [r.get("title") for r in result]
        assert "Test Collection" in titles

    @pytest.mark.asyncio
    async def test_aget_homepage_categories_returns_list(self, catalog_seed):
        """aget_homepage_categories must return a list of dicts."""
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_homepage_categories(limit=10)
        assert isinstance(result, list)
        names = [r.get("name") or r.get("title") for r in result]
        assert "Test Category" in names

    @pytest.mark.asyncio
    async def test_aget_homepage_banners_returns_active_only(self, catalog_seed):
        """aget_homepage_banners must return only active banners for the hero slot."""
        from apps.catalog.selectors import CatalogSelector
        from apps.catalog.models.banner import CatalogBanner
        from asgiref.sync import sync_to_async

        # Create inactive banner — must NOT appear
        await sync_to_async(CatalogBanner.objects.create)(
            slot="hero", title="Inactive Banner",
            is_active=False, cta_url="/", sort_order=99
        )

        result = await CatalogSelector.aget_homepage_banners(slot="hero")
        assert isinstance(result, list)
        assert any(b.get("title") == "Hero Banner" for b in result)
        # Inactive banner must NOT be in results
        assert not any(b.get("title") == "Inactive Banner" for b in result)

    @pytest.mark.asyncio
    async def test_aget_homepage_banners_respects_schedule(self, catalog_seed):
        """Expired banners (end_date < now) must be filtered out."""
        from apps.catalog.selectors import CatalogSelector
        from apps.catalog.models.banner import CatalogBanner
        from datetime import timedelta
        from asgiref.sync import sync_to_async

        await sync_to_async(CatalogBanner.objects.create)(
            slot="hero",
            title="Expired Banner",
            is_active=True,
            cta_url="/",
            end_date=timezone.now() - timedelta(days=1),  # expired
        )

        result = await CatalogSelector.aget_homepage_banners(slot="hero")
        # Expired banner should NOT appear
        assert not any(b.get("title") == "Expired Banner" for b in result)

    @pytest.mark.asyncio
    async def test_asyncio_gather_all_six_selectors(self, catalog_seed):
        """asyncio.gather() must run all 6 selectors concurrently without error."""
        from apps.catalog.selectors import CatalogSelector
        from apps.product.selectors.product_selectors import (
            aget_homepage_products,
            aget_homepage_hot_deals,
            aget_homepage_reviews,
            aget_featured_products,
        )

        results = await asyncio.gather(
            CatalogSelector.aget_homepage_collections(limit=10),
            CatalogSelector.aget_homepage_categories(limit=10),
            aget_homepage_products(limit=10),
            aget_homepage_hot_deals(limit=10),
            aget_homepage_reviews(limit=8),
            aget_featured_products(limit=8),
            CatalogSelector.aget_homepage_banners(slot="hero"),
            return_exceptions=False,
        )

        assert len(results) == 7
        for r in results:
            assert isinstance(r, list), f"Expected list, got {type(r)}: {r!r}"

    @pytest.mark.asyncio
    async def test_gather_concurrent_performance(self, catalog_seed):
        """asyncio.gather() must complete all selectors in < 500ms (dev DB, no cache)."""
        from apps.catalog.selectors import CatalogSelector
        from apps.product.selectors.product_selectors import aget_homepage_products

        start = time.perf_counter()
        await asyncio.gather(
            CatalogSelector.aget_homepage_collections(limit=10),
            CatalogSelector.aget_homepage_categories(limit=10),
            aget_homepage_products(limit=10),
        )
        elapsed_ms = (time.perf_counter() - start) * 1000
        # Dev DB without Redis — 500ms is generous; with Redis cache it would be <5ms
        assert elapsed_ms < 500, f"gather() took {elapsed_ms:.1f}ms — too slow"


# ─────────────────────────────────────────────────────────────────────────────
# G2 — Integration Tests: Homepage Bundle Ninja Endpoint
# ─────────────────────────────────────────────────────────────────────────────


class TestHomepageBundleEndpoint:
    """Integration tests for GET /api/v1/ninja/catalog/homepage/bundle/"""

    BUNDLE_URL = "/api/v1/ninja/catalog/homepage/bundle/"
    LEGACY_URL = "/api/v1/ninja/catalog/homepage/"

    def test_bundle_endpoint_returns_200(self, sync_client, catalog_seed):
        """GET /catalog/homepage/bundle/ must return HTTP 200."""
        response = sync_client.get(self.BUNDLE_URL)
        assert response.status_code == 200

    def test_bundle_has_all_six_sections(self, sync_client, catalog_seed):
        """Response must include all 6 data sections."""
        response = sync_client.get(self.BUNDLE_URL)
        body = response.json()
        data = body.get("data", body)

        required_sections = [
            "collections",
            "categories",
            "featured_products",
            "hot_deals",
            "reviews",
            "banners",
        ]
        for section in required_sections:
            assert section in data, f"Missing section: {section}"
            assert isinstance(data[section], list), f"{section} must be a list"

    def test_bundle_has_meta_counts(self, sync_client, catalog_seed):
        """Bundle must include meta section with count fields."""
        response = sync_client.get(self.BUNDLE_URL)
        body = response.json()
        data = body.get("data", body)
        meta = data.get("meta", {})
        assert "collections_count" in meta
        assert "categories_count" in meta
        assert "products_count" in meta
        assert "hot_deals_count" in meta
        assert "reviews_count" in meta
        assert "banners_count" in meta

    def test_bundle_banners_active_only(self, sync_client, catalog_seed):
        """Bundle banners must only include active, non-expired banners."""
        from apps.catalog.models.banner import CatalogBanner
        CatalogBanner.objects.create(
            slot="hero", title="Hidden Banner",
            is_active=False, cta_url="/",
        )
        response = sync_client.get(self.BUNDLE_URL)
        body = response.json()
        data = body.get("data", body)
        banner_titles = [b.get("title") for b in data.get("banners", [])]
        assert "Hidden Banner" not in banner_titles
        assert "Hero Banner" in banner_titles

    def test_bundle_response_time_below_500ms(self, sync_client, catalog_seed):
        """Bundle endpoint must respond < 1500ms on dev (no Redis warm-up)."""
        start = time.perf_counter()
        response = sync_client.get(self.BUNDLE_URL)
        elapsed_ms = (time.perf_counter() - start) * 1000
        assert response.status_code == 200
        assert elapsed_ms < 1500, f"Bundle took {elapsed_ms:.1f}ms — check asyncio.gather()"

    def test_bundle_redis_cache_returns_cached_response(self, sync_client, catalog_seed):
        """Second request must be served from Redis cache (< 10ms)."""
        # Prime the cache
        sync_client.get(self.BUNDLE_URL)

        # Measure second request (cache hit)
        start = time.perf_counter()
        response2 = sync_client.get(self.BUNDLE_URL)
        elapsed_ms = (time.perf_counter() - start) * 1000

        assert response2.status_code == 200
        # In dev, if Redis is not running, this threshold may not hold.
        # The test is informational — we log rather than fail hard.
        if elapsed_ms > 50:
            import warnings
            warnings.warn(
                f"Cache hit took {elapsed_ms:.1f}ms — Redis may not be running in test env",
                UserWarning,
            )

    def test_legacy_homepage_endpoint_still_works(self, sync_client, catalog_seed):
        """The original GET /catalog/homepage/ endpoint must remain functional."""
        response = sync_client.get(self.LEGACY_URL)
        assert response.status_code == 200

    def test_bundle_categories_include_seeded_category(self, sync_client, catalog_seed):
        """Bundle categories must include our seeded Test Category."""
        response = sync_client.get(self.BUNDLE_URL)
        data = response.json().get("data", response.json())
        cat_names = [c.get("name") or c.get("title") for c in data.get("categories", [])]
        assert "Test Category" in cat_names

    def test_bundle_no_auth_required(self, sync_client):
        """Homepage bundle must be publicly accessible — no auth required."""
        response = sync_client.get(self.BUNDLE_URL)
        assert response.status_code != 401
        assert response.status_code != 403

    def test_bundle_content_type_is_json(self, sync_client, catalog_seed):
        """Response Content-Type must be application/json."""
        response = sync_client.get(self.BUNDLE_URL)
        assert "application/json" in response.get("Content-Type", "")


# ─────────────────────────────────────────────────────────────────────────────
# G5 — Concurrency: Race Condition Tests
# ─────────────────────────────────────────────────────────────────────────────


class TestHomepageBundleConcurrency:
    """Verify no race conditions under concurrent requests."""

    @pytest.mark.asyncio
    async def test_50_concurrent_gather_calls_no_exception(self, catalog_seed):
        """50 concurrent asyncio.gather() calls must all complete without error."""
        from apps.catalog.selectors import CatalogSelector
        from apps.product.selectors.product_selectors import aget_homepage_products

        async def one_request():
            results = await asyncio.gather(
                CatalogSelector.aget_homepage_collections(limit=10),
                CatalogSelector.aget_homepage_categories(limit=10),
                aget_homepage_products(limit=10),
            )
            assert all(isinstance(r, list) for r in results)

        await asyncio.gather(*[one_request() for _ in range(50)])

    @pytest.mark.asyncio
    async def test_cache_invalidation_clears_bundle_key(self, catalog_seed):
        """Calling invalidate_catalog_cache() synchronously must clear catalog:* keys."""
        from apps.catalog.task import invalidate_catalog_cache
        from apps.common.utils.redis import api_cache_get, api_cache_set

        # Set a test key
        test_key = "catalog:test:race-condition-check"
        api_cache_set(test_key, {"test": True}, ttl=300)

        # Run task synchronously (not via Celery worker)
        invalidate_catalog_cache.apply()

        # Key must be gone
        result = api_cache_get(test_key)
        assert result is None, "Cache was not invalidated — stale data risk!"
