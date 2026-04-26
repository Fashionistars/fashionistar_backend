from django.utils import timezone
from django.db import connection
from django.test import override_settings
import pytest
from rest_framework.test import APIClient

from apps.catalog.models import BlogPost, BlogPostStatus, Brand, Category, Collections

pytestmark = pytest.mark.django_db(transaction=True)


@pytest.fixture(autouse=True)
def catalog_legacy_tables(transactional_db):
    existing_tables = set(connection.introspection.table_names())
    models = (Brand, Category, Collections)
    with connection.schema_editor() as schema_editor:
        for model in models:
            if model._meta.db_table not in existing_tables:
                schema_editor.create_model(model)
                existing_tables.add(model._meta.db_table)


def _payload(response):
    body = response.json()
    return body.get("data", body)


@override_settings(ROOT_URLCONF="apps.catalog.urls")
def test_catalog_public_lists_return_normalized_metadata(db):
    Category.objects.create(name="Gowns", active=True, cloudinary_url="https://cdn.example/gowns.jpg")
    Brand.objects.create(title="House of Ada", active=True, cloudinary_url="https://cdn.example/brand.jpg")
    Collections.objects.create(
        title="Wedding Edit",
        sub_title="Ceremony pieces",
        description="Curated occasion wear",
        cloudinary_url="https://cdn.example/collection.jpg",
    )
    BlogPost.objects.create(
        title="How Digital Measurements Improve Tailor Fit",
        slug="digital-measurements-tailor-fit",
        excerpt="A practical guide to better fitting made-to-measure clothing.",
        content="Digital measurements help clients and tailors reduce sizing errors across the full order lifecycle.",
        status=BlogPostStatus.PUBLISHED,
        seo_description="Learn how Fashionistar measurements help tailors deliver better clothes.",
        published_at=timezone.now(),
        featured_image_cloudinary_url="https://cdn.example/blog.jpg",
    )

    client = APIClient()

    categories = client.get("/categories/")
    brands = client.get("/brands/")
    collections = client.get("/collections/")
    blog = client.get("/blog/")

    assert categories.status_code == 200
    assert brands.status_code == 200
    assert collections.status_code == 200
    assert blog.status_code == 200

    category_payload = _payload(categories)
    brand_payload = _payload(brands)
    collection_payload = _payload(collections)
    blog_payload = _payload(blog)

    assert category_payload[0]["name"] == "Gowns"
    assert category_payload[0]["title"] == "Gowns"
    assert category_payload[0]["image_url"] == "https://cdn.example/gowns.jpg"
    assert brand_payload[0]["name"] == "House of Ada"
    assert brand_payload[0]["image_url"] == "https://cdn.example/brand.jpg"
    assert collection_payload[0]["title"] == "Wedding Edit"
    assert collection_payload[0]["image_url"] == "https://cdn.example/collection.jpg"
    assert blog_payload[0]["title"] == "How Digital Measurements Improve Tailor Fit"
    assert blog_payload[0]["image_url"] == "https://cdn.example/blog.jpg"


@override_settings(ROOT_URLCONF="apps.catalog.urls")
def test_catalog_public_detail_uses_slug(db):
    category = Category.objects.create(name="Senator Wear", active=True)
    client = APIClient()

    response = client.get(f"/categories/{category.slug}/")

    assert response.status_code == 200
    assert _payload(response)["slug"] == category.slug


@override_settings(ROOT_URLCONF="apps.catalog.urls")
def test_catalog_write_requires_staff_user(db):
    client = APIClient()

    response = client.post("/categories/", {"name": "Restricted"}, format="json")

    assert response.status_code in {401, 403}
