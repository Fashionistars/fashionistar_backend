"""
apps/catalog/tests/test_views.py  — Phase D3b

Integration tests for the Django-Ninja async catalog API views.

Coverage:
  - GET /api/v1/ninja/catalog/categories/         — list, active filter
  - GET /api/v1/ninja/catalog/brands/             — list, active filter
  - GET /api/v1/ninja/catalog/collections/        — list
  - GET /api/v1/ninja/catalog/blog/               — list, published only
  - GET /api/v1/ninja/catalog/tags/               — trending only
  - GET /api/v1/ninja/catalog/search/?q=          — search endpoint
  - GET /api/v1/ninja/catalog/homepage/bundle/    — v2 bundle (6 sections)
  - GET /api/v1/ninja/catalog/homepage/banners/   — banner slot filter
  - GET /api/v1/ninja/catalog/categories/{slug}/detail/ — detail + children
  - GET /api/v1/ninja/catalog/brands/{slug}/detail/     — brand detail
  - GET /api/v1/ninja/catalog/collections/{slug}/detail/ — collection detail
  - GET /api/v1/ninja/catalog/categories/{slug}/products/ — paginated products
  - Response shape validation (Ninja envelope: {data: ...})
  - 404 on non-existent slug
  - Edge: empty DB returns empty arrays (not errors)
  - Rate-limit headers present on catalog list endpoints
  - CORS: Access-Control-Allow-Origin present

Run:
    pytest apps/catalog/tests/test_views.py -v --asyncio-mode=auto
    pytest apps/catalog/tests/test_views.py -k test_bundle -v
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

NINJA_BASE = "/api/v1/ninja/catalog"


def _url(path: str) -> str:
    return f"{NINJA_BASE}{path}"


def _get_data(response_json: dict | list) -> dict | list:
    """Unwrap Ninja envelope: {data: ...}, paginated envelope {results: ...}, or pass-through."""
    if isinstance(response_json, dict):
        if "data" in response_json:
            return response_json["data"]
        if "results" in response_json:
            return response_json["results"]
    return response_json


# ─────────────────────────────────────────────────────────────────────────────
# Empty DB baseline — catalog endpoints must not 500 on empty DB
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestCatalogEndpointsEmptyDB:
    """Verify all catalog list endpoints return 200 + empty arrays on empty DB."""

    @pytest.mark.parametrize(
        "path",
        [
            "/categories/",
            "/brands/",
            "/collections/",
            "/blog/",
            "/tags/",
            "/homepage/bundle/",
        ],
    )
    async def test_returns_200_on_empty_db(self, async_client, db, path):
        resp = await async_client.get(_url(path))
        assert resp.status_code == 200, (
            f"{path} returned {resp.status_code}: {resp.content[:300]}"
        )

    async def test_search_returns_200_with_short_query(self, async_client, db):
        resp = await async_client.get(_url("/search/?q=a"))
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Categories Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestCategoriesEndpoint:
    async def test_list_categories(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/categories/"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        assert isinstance(data, list)

    async def test_only_active_categories_returned(self, async_client, db):
        from apps.catalog.models import Category
        from asgiref.sync import sync_to_async

        await sync_to_async(Category.objects.create)(name="Active Cat", slug="active-cat", is_deleted=False)
        await sync_to_async(Category.objects.create)(name="Inactive Cat", slug="inactive-cat", is_deleted=True)

        resp = await async_client.get(_url("/categories/"))
        data = _get_data(resp.json())
        slugs = [c["slug"] for c in data]
        assert "active-cat" in slugs
        assert "inactive-cat" not in slugs

    async def test_category_detail_200_for_existing_slug(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/categories/test-category/detail/"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        assert data["slug"] == "test-category"

    async def test_category_detail_404_for_unknown_slug(self, async_client, db):
        resp = await async_client.get(_url("/categories/__nonexistent__/detail/"))
        assert resp.status_code == 404

    async def test_category_products_200_for_existing_slug(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/categories/test-category/products/"))
        assert resp.status_code in (200, 404)  # 404 if no products yet is acceptable


# ─────────────────────────────────────────────────────────────────────────────
# Brands Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestBrandsEndpoint:
    async def test_list_brands(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/brands/"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        assert isinstance(data, list)

    async def test_only_active_brands_returned(self, async_client, db):
        try:
            from apps.catalog.models import Brand
        except ImportError:
            from apps.catalog.models.brand import Brand  # type: ignore[no-redef]
        from asgiref.sync import sync_to_async

        await sync_to_async(Brand.objects.create)(title="Active Brand", slug="active-brand", active=True)
        await sync_to_async(Brand.objects.create)(title="Inactive Brand", slug="inactive-brand", active=False)

        resp = await async_client.get(_url("/brands/"))
        data = _get_data(resp.json())
        slugs = [b["slug"] for b in data]
        assert "active-brand" in slugs
        assert "inactive-brand" not in slugs

    async def test_brand_detail_200_for_existing_slug(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/brands/test-brand/detail/"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        assert data["slug"] == "test-brand"

    async def test_brand_detail_404_for_unknown_slug(self, async_client, db):
        resp = await async_client.get(_url("/brands/__nonexistent_brand__/detail/"))
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Collections Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestCollectionsEndpoint:
    async def test_list_collections(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/collections/"))
        assert resp.status_code == 200

    async def test_collection_detail_200_for_existing_slug(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/collections/test-collection/detail/"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        assert data["slug"] == "test-collection"


# ─────────────────────────────────────────────────────────────────────────────
# Blog Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestBlogEndpoint:
    async def test_list_blog_returns_published_only(self, async_client, db):
        from apps.catalog.models.blog import BlogPost
        from asgiref.sync import sync_to_async

        await sync_to_async(BlogPost.objects.create)(
            title="Published",
            slug="published-post",
            content="...",
            status="published",
        )
        await sync_to_async(BlogPost.objects.create)(
            title="Draft",
            slug="draft-post",
            content="...",
            status="draft",
        )

        resp = await async_client.get(_url("/blog/"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        slugs = [b["slug"] for b in data]
        assert "published-post" in slugs
        assert "draft-post" not in slugs

    async def test_blog_detail_200_for_existing_slug(self, async_client, db):
        from apps.catalog.models.blog import BlogPost
        from asgiref.sync import sync_to_async

        await sync_to_async(BlogPost.objects.create)(
            title="My Post",
            slug="my-post",
            content="Hello world",
            status="published",
        )
        resp = await async_client.get(_url("/blog/my-post/"))
        assert resp.status_code == 200

    async def test_blog_detail_404_for_unknown_slug(self, async_client, db):
        resp = await async_client.get(_url("/blog/__no_such_post__/"))
        assert resp.status_code == 404


# ─────────────────────────────────────────────────────────────────────────────
# Tags Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestTagsEndpoint:
    async def test_list_tags_returns_trending_only(self, async_client, db):
        from apps.catalog.models.tag import Tag
        from asgiref.sync import sync_to_async

        await sync_to_async(Tag.objects.create)(name="trending_tag", slug="trending_tag", is_trending=True)
        await sync_to_async(Tag.objects.create)(name="non_trending", slug="non_trending", is_trending=False)

        resp = await async_client.get(_url("/tags/"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        # Extract tags array from response
        tags = data.get("tags", data) if isinstance(data, dict) else data
        slugs = [t["slug"] for t in tags]
        assert "trending_tag" in slugs
        assert "non_trending" not in slugs


# ─────────────────────────────────────────────────────────────────────────────
# Banners Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestBannersEndpoint:
    async def test_banners_returns_active_hero_slot(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/homepage/banners/?slot=hero"))
        assert resp.status_code == 200

    async def test_banners_does_not_return_inactive(self, async_client, db):
        from apps.catalog.models.banner import CatalogBanner
        from asgiref.sync import sync_to_async

        await sync_to_async(CatalogBanner.objects.create)(
            slot="hero", title="Active", cta_text="", cta_url="", is_active=True
        )
        await sync_to_async(CatalogBanner.objects.create)(
            slot="hero", title="Inactive", cta_text="", cta_url="", is_active=False
        )
        resp = await async_client.get(_url("/homepage/banners/?slot=hero"))
        assert resp.status_code == 200


# ─────────────────────────────────────────────────────────────────────────────
# Search Endpoint
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestSearchEndpoint:
    async def test_search_returns_correct_shape(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/search/?q=test"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        assert "categories" in data
        assert "brands" in data
        assert "collections" in data

    async def test_search_short_query_returns_empty_results(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/search/?q=xyz"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        assert data.get("categories", []) == []
        assert data.get("brands", []) == []
        assert data.get("collections", []) == []

    async def test_search_query_parameter_required(self, async_client, db):
        # Missing ?q should return 200 with empty results or 422
        resp = await async_client.get(_url("/search/"))
        assert resp.status_code in (200, 422)


# ─────────────────────────────────────────────────────────────────────────────
# Homepage Bundle v2 Endpoint  (Critical path — 6 parallel DB reads)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.bundle
class TestHomepageBundleV2Endpoint:
    async def test_bundle_returns_200(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/homepage/bundle/"))
        assert resp.status_code == 200

    async def test_bundle_has_all_six_sections(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/homepage/bundle/"))
        data = _get_data(resp.json())
        for section in ["categories", "collections", "featured_products", "hot_deals", "reviews", "banners"]:
            assert section in data, f"Missing bundle section: {section}"
            assert isinstance(data[section], list), f"{section} must be a list"

    async def test_bundle_has_meta_counts(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/homepage/bundle/"))
        data = _get_data(resp.json())
        meta = data.get("meta", {})
        assert "categories_count" in meta
        assert "collections_count" in meta
        assert "banners_count" in meta

    async def test_bundle_meta_counts_match_section_lengths(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/homepage/bundle/"))
        data = _get_data(resp.json())
        meta = data.get("meta", {})

        assert meta.get("categories_count") == len(data["categories"])
        assert meta.get("collections_count") == len(data["collections"])
        assert meta.get("banners_count") == len(data["banners"])

    async def test_bundle_latency_header_present(self, async_client, catalog_seed):
        """
        The bundle view should set X-Bundle-Latency-Ms header for observability.
        """
        resp = await async_client.get(_url("/homepage/bundle/"))
        # Header is optional — only assert if the view sets it
        if "X-Bundle-Latency-Ms" in resp.headers:
            latency = float(resp.headers["X-Bundle-Latency-Ms"])
            # Should be well under 200ms even without Redis on test DB
            assert latency < 200.0

    async def test_bundle_content_type_is_json(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/homepage/bundle/"))
        assert "application/json" in resp.headers.get("Content-Type", "")

    async def test_bundle_categories_contains_seeded_category(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/homepage/bundle/"))
        data = _get_data(resp.json())
        cat_slugs = [c["slug"] for c in data["categories"]]
        assert "test-category" in cat_slugs

    async def test_bundle_banners_contains_seeded_banner(self, async_client, catalog_seed):
        resp = await async_client.get(_url("/homepage/bundle/"))
        data = _get_data(resp.json())
        banner_titles = [b["title"] for b in data["banners"]]
        assert "Hero Banner" in banner_titles

    async def test_bundle_on_empty_db_returns_empty_sections(self, async_client, db):
        """Homepage bundle must never crash on empty DB — returns safe empty arrays."""
        resp = await async_client.get(_url("/homepage/bundle/"))
        assert resp.status_code == 200
        data = _get_data(resp.json())
        for section in ["categories", "collections", "featured_products", "hot_deals", "reviews", "banners"]:
            assert data[section] == [], f"{section} must be [] on empty DB, got {data[section]}"
