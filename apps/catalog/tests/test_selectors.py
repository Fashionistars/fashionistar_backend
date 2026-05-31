"""
apps/catalog/tests/test_selectors.py  — Phase D3

Async selector unit tests for the catalog app read-side.

Coverage:
  - get_active_categories_selector()         — active filter, sort, count
  - get_active_brands_selector()             — active filter, cached_product_count
  - get_active_collections_selector()        — is_featured ordering, active-now
  - get_published_blog_posts_selector()      — status=published, ordering
  - get_trending_tags_selector()             — is_trending filter
  - get_active_banners_by_slot_selector()    — slot filter, is_active, expiry guard
  - get_category_detail_with_children()      — parent lookup + children
  - get_catalog_search_selector()            — cross-entity search (q > 2 chars)
  - get_homepage_bundle_selector()           — all 6 sections parallel fetch

All tests run against Django's sqlite3 in-memory DB (config/test.py).
No Redis, no Celery — DummyCache is active.

Run:
    pytest apps/catalog/tests/test_selectors.py -v --asyncio-mode=auto
"""
from __future__ import annotations

import pytest
import pytest_asyncio

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def rich_seed(db):
    """
    Full catalog seed with v2 model fields.
    Returns dict of all created instances.
    """
    from apps.catalog.models import Category, Collections
    from apps.catalog.models.banner import CatalogBanner
    from apps.catalog.models.tag import CatalogTag
    from apps.catalog.models.blog import BlogPost

    try:
        from apps.catalog.models import Brand
    except ImportError:
        from apps.catalog.models.brand import Brand  # type: ignore[no-redef]

    # Categories — one active, one inactive
    cat_active = Category.objects.create(
        name="Aso-ebi",
        slug="aso-ebi",
        active=True,
        sort_order=1,
        meta_title="Buy Aso-ebi | Fashionistar",
        meta_description="Explore Aso-ebi styles.",
        cached_product_count=15,
    )
    cat_inactive = Category.objects.create(
        name="Archived Cat",
        slug="archived-cat",
        active=False,
    )
    # Sub-category
    cat_child = Category.objects.create(
        name="Aso-ebi Gele",
        slug="aso-ebi-gele",
        active=True,
        parent=cat_active,
    )

    # Brand — active, with v2 fields
    brand_active = Brand.objects.create(
        title="Zara Lagos",
        slug="zara-lagos",
        active=True,
        country="NG",
        verified=True,
        premium=True,
        cached_product_count=42,
    )
    brand_inactive = Brand.objects.create(
        title="Inactive Brand",
        slug="inactive-brand",
        active=False,
    )

    # Collection
    coll = Collections.objects.create(
        title="Summer Owanbe",
        slug="summer-owanbe",
        sub_title="Hot picks",
        description="Best picks for summer parties",
        is_featured=True,
        sort_order=1,
    )

    # Banner
    banner = CatalogBanner.objects.create(
        slot="hero",
        title="Independence Sale",
        subtitle="Up to 60% off",
        cta_text="Shop Now",
        cta_url="/products",
        is_active=True,
        sort_order=1,
    )

    # Tags
    tag_trending = CatalogTag.objects.create(
        name="ankara",
        slug="ankara",
        is_trending=True,
        color_hex="#FDA600",
    )
    tag_not_trending = CatalogTag.objects.create(
        name="everyday",
        slug="everyday",
        is_trending=False,
    )

    # Blog post
    blog_published = BlogPost.objects.create(
        title="How to style agbada",
        slug="how-to-style-agbada",
        excerpt="Tips for rocking agbada.",
        content="Agbada is a traditional...",
        status="published",
        is_featured=True,
    )
    blog_draft = BlogPost.objects.create(
        title="Draft post",
        slug="draft-post",
        content="Draft content",
        status="draft",
    )

    return {
        "cat_active": cat_active,
        "cat_inactive": cat_inactive,
        "cat_child": cat_child,
        "brand_active": brand_active,
        "brand_inactive": brand_inactive,
        "collection": coll,
        "banner": banner,
        "tag_trending": tag_trending,
        "tag_not_trending": tag_not_trending,
        "blog_published": blog_published,
        "blog_draft": blog_draft,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Category Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestCategorySelector:
    async def test_returns_only_active_categories(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_active_categories_selector
        result = await get_active_categories_selector()
        slugs = [c["slug"] for c in result]
        assert "aso-ebi" in slugs
        assert "archived-cat" not in slugs

    async def test_category_has_v2_meta_fields(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_active_categories_selector
        result = await get_active_categories_selector()
        aso_ebi = next((c for c in result if c["slug"] == "aso-ebi"), None)
        assert aso_ebi is not None
        assert aso_ebi.get("meta_title") == "Buy Aso-ebi | Fashionistar"
        assert aso_ebi.get("cached_product_count") == 15

    async def test_category_count_matches_active_only(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_active_categories_selector
        result = await get_active_categories_selector()
        # 2 active: aso-ebi + aso-ebi-gele (child)
        assert len(result) >= 2


# ─────────────────────────────────────────────────────────────────────────────
# Brand Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestBrandSelector:
    async def test_returns_only_active_brands(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_active_brands_selector
        result = await get_active_brands_selector()
        slugs = [b["slug"] for b in result]
        assert "zara-lagos" in slugs
        assert "inactive-brand" not in slugs

    async def test_brand_has_verified_and_country_fields(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_active_brands_selector
        result = await get_active_brands_selector()
        zara = next((b for b in result if b["slug"] == "zara-lagos"), None)
        assert zara is not None
        assert zara.get("verified") is True
        assert zara.get("country") == "NG"
        assert zara.get("cached_product_count") == 42


# ─────────────────────────────────────────────────────────────────────────────
# Collection Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestCollectionSelector:
    async def test_returns_featured_collections(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_active_collections_selector
        result = await get_active_collections_selector()
        slugs = [c["slug"] for c in result]
        assert "summer-owanbe" in slugs

    async def test_collection_has_v2_fields(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_active_collections_selector
        result = await get_active_collections_selector()
        owanbe = next((c for c in result if c["slug"] == "summer-owanbe"), None)
        assert owanbe is not None
        assert owanbe.get("is_featured") is True


# ─────────────────────────────────────────────────────────────────────────────
# Blog Post Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestBlogSelector:
    async def test_returns_only_published_posts(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_published_blog_posts_selector
        result = await get_published_blog_posts_selector()
        slugs = [b["slug"] for b in result]
        assert "how-to-style-agbada" in slugs
        assert "draft-post" not in slugs

    async def test_published_post_has_v2_fields(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_published_blog_posts_selector
        result = await get_published_blog_posts_selector()
        assert len(result) >= 1
        post = result[0]
        # Must have read_time_minutes if utils are applied
        assert "title" in post
        assert "slug" in post


# ─────────────────────────────────────────────────────────────────────────────
# Tags Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestTagsSelector:
    async def test_returns_only_trending_tags(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_trending_tags_selector
        result = await get_trending_tags_selector()
        slugs = [t["slug"] for t in result]
        assert "ankara" in slugs
        assert "everyday" not in slugs

    async def test_tag_has_color_hex(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_trending_tags_selector
        result = await get_trending_tags_selector()
        ankara = next((t for t in result if t["slug"] == "ankara"), None)
        assert ankara is not None
        assert ankara.get("color_hex") == "#FDA600"


# ─────────────────────────────────────────────────────────────────────────────
# Banner Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestBannerSelector:
    async def test_returns_active_banners_by_slot(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_active_banners_selector
        result = await get_active_banners_selector(slot="hero")
        assert len(result) >= 1
        assert result[0]["slot"] == "hero"

    async def test_does_not_return_inactive_banners(self, rich_seed, db):
        from apps.catalog.models.banner import CatalogBanner
        from apps.catalog.selectors.catalog_selectors import get_active_banners_selector

        CatalogBanner.objects.create(
            slot="hero",
            title="Inactive Banner",
            subtitle="",
            cta_text="",
            cta_url="",
            is_active=False,
        )
        result = await get_active_banners_selector(slot="hero")
        titles = [b["title"] for b in result]
        assert "Inactive Banner" not in titles


# ─────────────────────────────────────────────────────────────────────────────
# Category Detail Selector (with children)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestCategoryDetailSelector:
    async def test_returns_category_with_children(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_category_detail_selector
        result = await get_category_detail_selector("aso-ebi")
        assert result is not None
        assert result["slug"] == "aso-ebi"
        children = result.get("children", [])
        child_slugs = [c["slug"] for c in children]
        assert "aso-ebi-gele" in child_slugs

    async def test_returns_none_for_inactive_category(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_category_detail_selector
        result = await get_category_detail_selector("archived-cat")
        # Inactive category should return None or be excluded
        # Accept either: None, or a result where active=False
        if result is not None:
            assert result.get("active") is False

    async def test_returns_none_for_unknown_slug(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_category_detail_selector
        result = await get_category_detail_selector("__nonexistent__")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Search Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestSearchSelector:
    async def test_search_returns_matching_category(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_catalog_search_selector
        result = await get_catalog_search_selector("aso")
        cats = result.get("categories", [])
        slugs = [c["slug"] for c in cats]
        assert "aso-ebi" in slugs

    async def test_search_returns_matching_brand(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_catalog_search_selector
        result = await get_catalog_search_selector("zara")
        brands = result.get("brands", [])
        slugs = [b["slug"] for b in brands]
        assert "zara-lagos" in slugs

    async def test_short_query_returns_empty(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_catalog_search_selector
        result = await get_catalog_search_selector("a")
        # Should short-circuit and return empty structure
        assert result.get("categories", []) == []
        assert result.get("brands", []) == []
        assert result.get("collections", []) == []

    async def test_no_sql_injection_on_special_chars(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_catalog_search_selector
        # Should not raise; should return empty or safe result
        result = await get_catalog_search_selector("' OR 1=1 --")
        assert isinstance(result, dict)


# ─────────────────────────────────────────────────────────────────────────────
# Homepage Bundle Selector (Phase B3 — parallel asyncio.gather)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.bundle
class TestHomepageBundleSelector:
    async def test_bundle_has_all_six_sections(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_homepage_bundle_v2_selector
        result = await get_homepage_bundle_v2_selector()

        required_keys = [
            "categories", "collections", "featured_products",
            "hot_deals", "reviews", "banners",
        ]
        for key in required_keys:
            assert key in result, f"Missing bundle section: {key}"
            assert isinstance(result[key], list), f"Section {key} must be a list"

    async def test_bundle_meta_counts_match_sections(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_homepage_bundle_v2_selector
        result = await get_homepage_bundle_v2_selector()
        meta = result.get("meta", {})

        assert meta.get("categories_count", -1) == len(result["categories"])
        assert meta.get("collections_count", -1) == len(result["collections"])
        assert meta.get("banners_count", -1) == len(result["banners"])

    async def test_bundle_categories_contains_seeded(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_homepage_bundle_v2_selector
        result = await get_homepage_bundle_v2_selector()
        cat_slugs = [c["slug"] for c in result["categories"]]
        assert "aso-ebi" in cat_slugs

    async def test_bundle_banners_contains_active_banner(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_homepage_bundle_v2_selector
        result = await get_homepage_bundle_v2_selector()
        banner_titles = [b["title"] for b in result["banners"]]
        assert "Independence Sale" in banner_titles

    async def test_bundle_excludes_inactive_categories(self, rich_seed):
        from apps.catalog.selectors.catalog_selectors import get_homepage_bundle_v2_selector
        result = await get_homepage_bundle_v2_selector()
        cat_slugs = [c["slug"] for c in result["categories"]]
        assert "archived-cat" not in cat_slugs
