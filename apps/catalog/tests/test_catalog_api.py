from rest_framework.test import APIClient

from apps.admin_backend.models import Brand, Category, Collections


def _payload(response):
    body = response.json()
    return body.get("data", body)


def test_catalog_public_lists_return_normalized_metadata(db):
    Category.objects.create(name="Gowns", active=True, cloudinary_url="https://cdn.example/gowns.jpg")
    Brand.objects.create(title="House of Ada", active=True, cloudinary_url="https://cdn.example/brand.jpg")
    Collections.objects.create(
        title="Wedding Edit",
        sub_title="Ceremony pieces",
        description="Curated occasion wear",
        cloudinary_url="https://cdn.example/collection.jpg",
    )

    client = APIClient()

    categories = client.get("/api/v1/catalog/categories/")
    brands = client.get("/api/v1/catalog/brands/")
    collections = client.get("/api/v1/catalog/collections/")

    assert categories.status_code == 200
    assert brands.status_code == 200
    assert collections.status_code == 200

    category_payload = _payload(categories)
    brand_payload = _payload(brands)
    collection_payload = _payload(collections)

    assert category_payload[0]["name"] == "Gowns"
    assert category_payload[0]["title"] == "Gowns"
    assert category_payload[0]["image_url"] == "https://cdn.example/gowns.jpg"
    assert brand_payload[0]["name"] == "House of Ada"
    assert brand_payload[0]["image_url"] == "https://cdn.example/brand.jpg"
    assert collection_payload[0]["title"] == "Wedding Edit"
    assert collection_payload[0]["image_url"] == "https://cdn.example/collection.jpg"


def test_catalog_public_detail_uses_slug(db):
    category = Category.objects.create(name="Senator Wear", active=True)
    client = APIClient()

    response = client.get(f"/api/v1/catalog/categories/{category.slug}/")

    assert response.status_code == 200
    assert _payload(response)["slug"] == category.slug


def test_catalog_write_requires_staff_user(db):
    client = APIClient()

    response = client.post("/api/v1/catalog/categories/", {"name": "Restricted"}, format="json")

    assert response.status_code in {401, 403}
