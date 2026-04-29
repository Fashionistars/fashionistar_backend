from django.utils import timezone
from django.db import connection
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


def test_catalog_public_lists_return_normalized_metadata(db):
    Category.objects.create(name="Gowns", active=True)
    Brand.objects.create(title="House of Ada", active=True)
    Collections.objects.create(
        title="Wedding Edit",
        sub_title="Ceremony pieces",
        description="Curated occasion wear",
    )
    BlogPost.objects.create(
        title="How Digital Measurements Improve Tailor Fit",
        slug="digital-measurements-tailor-fit",
        excerpt="A practical guide to better fitting made-to-measure clothing.",
        content="Digital measurements help clients and tailors reduce sizing errors across the full order lifecycle.",
        status=BlogPostStatus.PUBLISHED,
        seo_description="Learn how Fashionistar measurements help tailors deliver better clothes.",
        published_at=timezone.now(),
    )

    client = APIClient()

    categories = client.get("/api/v1/ninja/catalog/categories/")
    brands = client.get("/api/v1/ninja/catalog/brands/")
    collections = client.get("/api/v1/ninja/catalog/collections/")
    blog = client.get("/api/v1/ninja/catalog/blog/")

    assert categories.status_code == 200
    assert brands.status_code == 200
    assert collections.status_code == 200
    assert blog.status_code == 200

    category_payload = _payload(categories)
    brand_payload = _payload(brands)
    collection_payload = _payload(collections)
    blog_payload = _payload(blog)

    assert category_payload["results"][0]["name"] == "Gowns"
    assert category_payload["results"][0]["title"] == "Gowns"
    assert category_payload["results"][0]["image_url"] == ""
    assert brand_payload["results"][0]["name"] == "House of Ada"
    assert brand_payload["results"][0]["image_url"] == ""
    assert collection_payload["results"][0]["title"] == "Wedding Edit"
    assert collection_payload["results"][0]["image_url"] == ""
    assert blog_payload["results"][0]["title"] == "How Digital Measurements Improve Tailor Fit"
    assert blog_payload["results"][0]["image_url"] == ""


def test_catalog_public_detail_uses_slug(db):
    category = Category.objects.create(name="Senator Wear", active=True)
    client = APIClient()

    response = client.get(f"/api/v1/ninja/catalog/categories/{category.slug}/")

    assert response.status_code == 200
    assert _payload(response)["slug"] == category.slug


def test_catalog_write_requires_staff_user(db):
    client = APIClient()

    response = client.post("/api/v1/catalog/categories/", {"name": "Restricted"}, format="json")

    assert response.status_code in {401, 403}
