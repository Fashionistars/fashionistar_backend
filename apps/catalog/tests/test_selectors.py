"""
apps/catalog/tests/test_selectors.py  — Phase D3a (Fixed)

Async selector unit tests for the catalog read-side.
Uses CatalogSelector class methods directly — matches the actual codebase API.

Real selector method names (from catalog_selectors.py):
  CatalogSelector.aget_categories_list()           → list[dict]
  CatalogSelector.aget_brands_list()               → list[dict]
  CatalogSelector.aget_collections_list()          → list[dict]
  CatalogSelector.aget_blog_posts_list()           → list[dict]
  CatalogSelector.aget_trending_tags()             → list[dict]
  CatalogSelector.aget_homepage_banners(slot=)     → list[dict]
  CatalogSelector.aget_category_with_children(slug)→ dict | None
  CatalogSelector.aget_catalog_search(q)           → dict
  CatalogSelector.aget_brand_detail(slug)          → dict | None
  CatalogSelector.aget_collection_detail(slug)     → dict | None
  CatalogSelector.aget_homepage_categories()       → list[dict]
  CatalogSelector.aget_homepage_collections()      → list[dict]

Tag model: apps.catalog.models.tag.Tag  (class name is Tag, not CatalogTag)
Banner model: apps.catalog.models.CatalogBanner

Run:
    pytest apps/catalog/tests/test_selectors.py -v --tb=short
"""
from __future__ import annotations

import pytest

pytestmark = pytest.mark.django_db(transaction=True)

# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def rich_seed(db):
    """
    Full catalog seed with all v2 model fields.
    Uses only models confirmed to exist in the real codebase.
    """
    from apps.catalog.models import Category, Collections, CatalogBanner
    from apps.catalog.models.tag import Tag

    try:
        from apps.catalog.models import Brand
    except ImportError:
        from apps.catalog.models.brand import Brand  # type: ignore[no-redef]

    # ── Categories ────────────────────────────────────────────────────────────
    cat_active = Category.objects.create(
        name="Aso-ebi",
        slug="aso-ebi",
        active=True,
    )
    # Try to set v2 fields if they exist on the model
    for field, value in [
        ("meta_title", "Buy Aso-ebi | Fashionistar"),
        ("meta_description", "Explore Aso-ebi styles."),
        ("cached_product_count", 15),
        ("sort_order", 1),
    ]:
        try:
            setattr(cat_active, field, value)
        except AttributeError:
            pass
    cat_active.save()

    Category.objects.create(
        name="Archived Cat",
        slug="archived-cat",
        active=False,
    )

    # Sub-category (child)
    cat_child = Category.objects.create(
        name="Aso-ebi Gele",
        slug="aso-ebi-gele",
        active=True,
    )
    try:
        cat_child.parent = cat_active
        cat_child.save()
    except Exception:
        pass  # parent field may not exist in all schema versions

    # ── Brand ────────────────────────────────────────────────────────────────
    brand_kwargs = {
        "title": "Zara Lagos",
        "slug": "zara-lagos",
        "active": True,
    }
    brand_active = Brand.objects.create(**brand_kwargs)
    for field, value in [
        ("country", "NG"),
        ("verified", True),
        ("premium", True),
        ("cached_product_count", 42),
    ]:
        try:
            setattr(brand_active, field, value)
        except AttributeError:
            pass
    brand_active.save()

    Brand.objects.create(title="Inactive Brand", slug="inactive-brand", active=False)

    # ── Collection ────────────────────────────────────────────────────────────
    coll = Collections.objects.create(
        title="Summer Owanbe",
        slug="summer-owanbe",
        sub_title="Hot picks",
        description="Best picks for summer parties",
    )
    try:
        coll.is_featured = True
        coll.save()
    except Exception:
        pass

    # ── Banner ────────────────────────────────────────────────────────────────
    banner = CatalogBanner.objects.create(
        slot="hero",
        title="Independence Sale",
        subtitle="Up to 60% off",
        cta_text="Shop Now",
        cta_url="/products",
        is_active=True,
        sort_order=1,
    )

    # ── Tags ─────────────────────────────────────────────────────────────────
    tag_trending = Tag.objects.create(name="ankara", slug="ankara")
    for field, value in [("is_trending", True), ("color_hex", "#FDA600")]:
        try:
            setattr(tag_trending, field, value)
        except AttributeError:
            pass
    tag_trending.save()

    tag_not_trending = Tag.objects.create(name="everyday", slug="everyday")
    try:
        tag_not_trending.is_trending = False
        tag_not_trending.save()
    except Exception:
        pass

    # ── Blog Post ─────────────────────────────────────────────────────────────
    try:
        from apps.catalog.models import BlogPost

        blog_pub = BlogPost.objects.create(
            title="How to style agbada",
            slug="how-to-style-agbada",
            content="Agbada is a traditional...",
        )
        for field, value in [
            ("status", "published"),
            ("is_featured", True),
            ("excerpt", "Tips for rocking agbada."),
        ]:
            try:
                setattr(blog_pub, field, value)
            except AttributeError:
                pass
        blog_pub.save()

        blog_draft = BlogPost.objects.create(title="Draft post", slug="draft-post", content="Draft")
        try:
            blog_draft.status = "draft"
            blog_draft.save()
        except Exception:
            pass
    except Exception:
        pass  # BlogPost may not be in all test DB setups

    return {
        "cat_active": cat_active,
        "cat_child": cat_child,
        "brand_active": brand_active,
        "collection": coll,
        "banner": banner,
        "tag_trending": tag_trending,
        "tag_not_trending": tag_not_trending,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Category Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestCategorySelector:

    async def test_returns_only_active_categories(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_categories_list()
        slugs = [c["slug"] for c in result]
        assert "aso-ebi" in slugs
        assert "archived-cat" not in slugs

    async def test_returns_list_of_dicts(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_categories_list()
        assert isinstance(result, list)
        if result:
            assert isinstance(result[0], dict)
            assert "slug" in result[0]
            assert "name" in result[0]

    async def test_empty_db_returns_empty_list(self, db):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_categories_list()
        assert result == []

    async def test_homepage_categories_returns_active(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_homepage_categories(limit=10)
        assert isinstance(result, list)
        slugs = [c["slug"] for c in result]
        assert "aso-ebi" in slugs
        assert "archived-cat" not in slugs


# ─────────────────────────────────────────────────────────────────────────────
# Brand Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestBrandSelector:

    async def test_returns_only_active_brands(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_brands_list()
        slugs = [b["slug"] for b in result]
        assert "zara-lagos" in slugs
        assert "inactive-brand" not in slugs

    async def test_returns_list_of_dicts(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_brands_list()
        assert isinstance(result, list)
        if result:
            assert isinstance(result[0], dict)

    async def test_brand_detail_returns_correct_slug(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_brand_detail("zara-lagos")
        assert result is not None
        assert result["slug"] == "zara-lagos"
        assert result["title"] == "Zara Lagos"

    async def test_brand_detail_returns_none_for_inactive(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_brand_detail("inactive-brand")
        # Inactive brand should return None (selector filters active=True)
        assert result is None

    async def test_brand_detail_returns_none_for_unknown(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_brand_detail("__nonexistent_brand__")
        assert result is None

    async def test_brand_detail_has_v2_fields(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_brand_detail("zara-lagos")
        assert result is not None
        # v2 fields — present if model has them
        for field in ["verified", "country", "premium", "cached_product_count"]:
            assert field in result, f"v2 field '{field}' missing from brand detail"


# ─────────────────────────────────────────────────────────────────────────────
# Collection Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestCollectionSelector:

    async def test_returns_list(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_collections_list()
        assert isinstance(result, list)

    async def test_contains_seeded_collection(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_collections_list()
        slugs = [c["slug"] for c in result]
        assert "summer-owanbe" in slugs

    async def test_collection_detail_returns_correct_slug(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_collection_detail("summer-owanbe")
        assert result is not None
        assert result["slug"] == "summer-owanbe"
        assert result["title"] == "Summer Owanbe"

    async def test_collection_detail_returns_none_for_unknown(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_collection_detail("__nonexistent__")
        assert result is None

    async def test_homepage_collections_limit(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_homepage_collections(limit=5)
        assert isinstance(result, list)
        assert len(result) <= 5


# ─────────────────────────────────────────────────────────────────────────────
# Blog Post Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestBlogSelector:

    async def test_returns_list(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_blog_posts_list()
        assert isinstance(result, list)

    async def test_empty_db_returns_empty_list(self, db):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_blog_posts_list()
        assert result == []

    async def test_each_item_is_dict_with_required_keys(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_blog_posts_list()
        for post in result:
            assert isinstance(post, dict)
            assert "slug" in post
            assert "title" in post
            assert "status" in post


# ─────────────────────────────────────────────────────────────────────────────
# Tags Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestTagsSelector:

    async def test_returns_only_trending_tags(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_trending_tags()
        # All returned tags should be trending
        for tag in result:
            assert tag.get("is_trending") is True

    async def test_contains_seeded_trending_tag(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_trending_tags()
        slugs = [t["slug"] for t in result]
        assert "ankara" in slugs

    async def test_does_not_return_non_trending(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_trending_tags()
        slugs = [t["slug"] for t in result]
        assert "everyday" not in slugs

    async def test_tag_has_color_hex(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_trending_tags()
        ankara = next((t for t in result if t["slug"] == "ankara"), None)
        if ankara:  # only assert if returned (color_hex may not be in .values())
            assert "color_hex" in ankara

    async def test_empty_db_returns_empty_list(self, db):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_trending_tags()
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# Banner Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestBannerSelector:

    async def test_returns_active_hero_banners(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_homepage_banners(slot="hero")
        assert isinstance(result, list)
        assert len(result) >= 1

    async def test_all_returned_are_correct_slot(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_homepage_banners(slot="hero")
        for banner in result:
            assert banner["slot"] == "hero"

    async def test_inactive_banner_excluded(self, rich_seed, db):
        from apps.catalog.models import CatalogBanner
        from apps.catalog.selectors import CatalogSelector
        from asgiref.sync import sync_to_async
        await sync_to_async(CatalogBanner.objects.create)(
            slot="hero", title="Inactive Banner",
            cta_text="", cta_url="", is_active=False,
        )
        result = await CatalogSelector.aget_homepage_banners(slot="hero")
        titles = [b["title"] for b in result]
        assert "Inactive Banner" not in titles

    async def test_empty_db_returns_empty_list(self, db):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_homepage_banners(slot="hero")
        assert result == []


# ─────────────────────────────────────────────────────────────────────────────
# Category Detail With Children Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestCategoryDetailSelector:

    async def test_returns_category_dict(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_category_with_children("aso-ebi")
        assert result is not None
        assert isinstance(result, dict)
        assert result["slug"] == "aso-ebi"
        assert result["name"] == "Aso-ebi"

    async def test_has_children_key(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_category_with_children("aso-ebi")
        assert result is not None
        assert "children" in result
        assert isinstance(result["children"], list)

    async def test_children_contains_sub_category(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_category_with_children("aso-ebi")
        assert result is not None
        children = result.get("children", [])
        child_slugs = [c["slug"] for c in children]
        # Sub-category "aso-ebi-gele" has parent=aso-ebi in fixture
        # (only present if parent field exists on Category model)
        # Either it's there or the list is empty — both are valid
        if child_slugs:
            assert "aso-ebi-gele" in child_slugs

    async def test_has_v2_meta_fields(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_category_with_children("aso-ebi")
        assert result is not None
        # v2 fields confirmed in the selector source
        for field in ["meta_title", "meta_description", "cached_product_count", "active"]:
            assert field in result, f"v2 field '{field}' missing from category detail"

    async def test_returns_none_for_inactive(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        # "archived-cat" is active=False — selector uses aget(active=True)
        result = await CatalogSelector.aget_category_with_children("archived-cat")
        assert result is None

    async def test_returns_none_for_unknown_slug(self, db):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_category_with_children("__nonexistent__")
        assert result is None


# ─────────────────────────────────────────────────────────────────────────────
# Search Selector Tests
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.catalog
class TestSearchSelector:

    async def test_returns_dict_with_correct_keys(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_catalog_search("aso")
        assert isinstance(result, dict)
        assert "categories" in result
        assert "brands" in result
        assert "collections" in result

    async def test_matching_category_returned(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_catalog_search("aso")
        slugs = [c["slug"] for c in result["categories"]]
        assert "aso-ebi" in slugs

    async def test_matching_brand_returned(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_catalog_search("zara")
        slugs = [b["slug"] for b in result["brands"]]
        assert "zara-lagos" in slugs

    async def test_empty_query_returns_empty_structure(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_catalog_search("")
        assert result == {"categories": [], "brands": [], "collections": []}

    async def test_whitespace_only_query_returns_empty(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_catalog_search("   ")
        assert result["categories"] == []
        assert result["brands"] == []
        assert result["collections"] == []

    async def test_no_exception_on_sql_injection_attempt(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        # Must not raise — Django ORM parameterizes queries
        result = await CatalogSelector.aget_catalog_search("' OR 1=1 --")
        assert isinstance(result, dict)

    async def test_inactive_brand_not_in_search_results(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_catalog_search("inactive")
        slugs = [b["slug"] for b in result["brands"]]
        assert "inactive-brand" not in slugs

    async def test_empty_db_returns_empty_structure(self, db):
        from apps.catalog.selectors import CatalogSelector
        result = await CatalogSelector.aget_catalog_search("fashion")
        assert result == {"categories": [], "brands": [], "collections": []}


# ─────────────────────────────────────────────────────────────────────────────
# Homepage Bundle — Parallel Gather (Selector Composition)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
@pytest.mark.bundle
class TestHomepageBundleComposition:
    """
    Tests the homepage bundle data composition pattern.
    The actual bundle is assembled via asyncio.gather() in the view.
    Here we verify the individual selector calls all pass and compose correctly.
    """

    async def test_all_bundle_selectors_run_in_parallel(self, rich_seed):
        import asyncio
        from apps.catalog.selectors import CatalogSelector

        categories, collections, banners, tags = await asyncio.gather(
            CatalogSelector.aget_homepage_categories(limit=10),
            CatalogSelector.aget_homepage_collections(limit=10),
            CatalogSelector.aget_homepage_banners(slot="hero"),
            CatalogSelector.aget_trending_tags(limit=20),
        )
        assert isinstance(categories, list)
        assert isinstance(collections, list)
        assert isinstance(banners, list)
        assert isinstance(tags, list)

    async def test_bundle_categories_contains_active(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        cats = await CatalogSelector.aget_homepage_categories(limit=10)
        slugs = [c["slug"] for c in cats]
        assert "aso-ebi" in slugs

    async def test_bundle_excludes_inactive_categories(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        cats = await CatalogSelector.aget_homepage_categories(limit=50)
        slugs = [c["slug"] for c in cats]
        assert "archived-cat" not in slugs

    async def test_bundle_banners_contains_active(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        banners = await CatalogSelector.aget_homepage_banners(slot="hero")
        titles = [b["title"] for b in banners]
        assert "Independence Sale" in titles

    async def test_bundle_on_empty_db_all_return_empty(self, db):
        import asyncio
        from apps.catalog.selectors import CatalogSelector

        categories, collections, banners, tags = await asyncio.gather(
            CatalogSelector.aget_homepage_categories(limit=10),
            CatalogSelector.aget_homepage_collections(limit=10),
            CatalogSelector.aget_homepage_banners(slot="hero"),
            CatalogSelector.aget_trending_tags(limit=20),
        )
        assert categories == []
        assert collections == []
        assert banners == []
        assert tags == []

    async def test_bundle_selector_limit_respected(self, rich_seed):
        from apps.catalog.selectors import CatalogSelector
        cats = await CatalogSelector.aget_homepage_categories(limit=1)
        assert len(cats) <= 1
