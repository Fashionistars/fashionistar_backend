from __future__ import annotations

import pytest


@pytest.mark.django_db
def test_brand_product_count_alias_uses_cached_counter():
    from apps.catalog.models import Brand

    brand = Brand.objects.create(title="Alias Brand", cached_product_count=14)

    assert brand.product_count == 14


@pytest.mark.django_db
def test_collection_catalog_tags_and_product_count_alias():
    from apps.catalog.models import Collections, Tag

    collection = Collections.objects.create(title="Luxury Capsule", cached_product_count=3)
    tag = Tag.objects.create(name="Luxury", slug="luxury")
    collection.catalog_tags.add(tag)

    assert collection.product_count == 3
    assert list(collection.catalog_tags.values_list("slug", flat=True)) == ["luxury"]


@pytest.mark.django_db
def test_blogpost_metadata_aliases_and_resolved_tags_prefer_relations():
    from apps.catalog.models import BlogPost, Tag

    post = BlogPost.objects.create(
        title="Enterprise Styling",
        slug="enterprise-styling",
        content="word " * 500,
        seo_title="Enterprise Styling SEO",
        seo_description="Enterprise styling description",
        tags=["legacy-style", "precision-fit"],
    )
    related_tag = Tag.objects.create(name="Precision", slug="precision")
    post.catalog_tags.add(related_tag)

    assert post.meta_title == "Enterprise Styling SEO"
    assert post.meta_description == "Enterprise styling description"
    assert post.read_time_minutes >= 2
    assert post.resolved_tags == ["Precision"]


@pytest.mark.django_db
def test_blogpost_resolved_tags_falls_back_to_legacy_json_tags():
    from apps.catalog.models import BlogPost

    post = BlogPost.objects.create(
        title="Legacy Tag Post",
        slug="legacy-tag-post",
        content="tailor " * 200,
        tags=["  ready-to-wear ", "", "measurements"],
    )

    assert post.resolved_tags == ["ready-to-wear", "measurements"]
