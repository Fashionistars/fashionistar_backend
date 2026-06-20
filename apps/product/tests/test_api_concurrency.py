# apps/product/tests/test_api_concurrency.py
import pytest
import uuid
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from django.contrib.auth import get_user_model
from apps.product.models import Product

User = get_user_model()

@pytest.fixture
def vendor_a_user(db):
    user = User.objects.create_user(
        email="vendor_a@fashionistar.com",
        password="Vendor1234!",
        role="vendor",
        is_active=True,
        is_verified=True,
    )
    from apps.vendor.models import VendorProfile
    VendorProfile.objects.create(
        user=user,
        store_name="Vendor A Tailoring",
        store_slug="vendor-a-tailoring",
    )
    return user

@pytest.fixture
def vendor_b_user(db):
    user = User.objects.create_user(
        email="vendor_b@fashionistar.com",
        password="Vendor1234!",
        role="vendor",
        is_active=True,
        is_verified=True,
    )
    from apps.vendor.models import VendorProfile
    VendorProfile.objects.create(
        user=user,
        store_name="Vendor B Tailoring",
        store_slug="vendor-b-tailoring",
    )
    return user

@pytest.fixture
def category(db):
    from apps.catalog.models import Category
    return Category.objects.create(name="African Wear", slug="african-wear")

@pytest.fixture
def vendor_b_product(db, vendor_b_user, category):
    from apps.product.models import Product, ProductStatus
    product = Product.objects.create(
        title="Vendor B Product",
        slug="vendor-b-product",
        description="Handcrafted royal blue Agbada",
        price=Decimal("45000.00"),
        currency="NGN",
        stock_qty=20,
        status=ProductStatus.PUBLISHED,
        vendor=vendor_b_user.vendor_profile,
    )
    product.categories.set([category])
    return product

@pytest.fixture(autouse=True)
def mock_idempotency_cache():
    import collections
    from django.core.cache.backends.locmem import LocMemCache
    from unittest.mock import patch

    test_cache = LocMemCache("fashionistar-test-idem", {})
    test_cache._cache = collections.OrderedDict()

    patcher = patch(
        "apps.authentication.middleware.idempotency._get_cache",
        return_value=test_cache,
    )
    patcher.start()
    yield test_cache
    patcher.stop()

@pytest.mark.django_db
class TestVendorAPIConcurrencyAndSecurity:
    """Security verification test suite ensuring absolute IDOR prevention and idempotency."""

    def test_idor_prevention_on_product_modification(self, api_client, vendor_a_user, vendor_b_product):
        """Asserts that Vendor A cannot update Vendor B's product resource."""
        api_client.force_authenticate(user=vendor_a_user)
        url = reverse("product:vendor-product-detail", kwargs={"slug": vendor_b_product.slug})
        
        payload = {"title": "Malicious Title Override Attempt"}
        response = api_client.patch(url, payload, format="json")
        
        # Verify forbidden (403) or not_found (404)
        assert response.status_code in [status.HTTP_403_FORBIDDEN, status.HTTP_404_NOT_FOUND]
        
        # Verify database value was NOT mutated
        vendor_b_product.refresh_from_db()
        assert vendor_b_product.title != "Malicious Title Override Attempt"

    def test_idempotency_middleware_prevents_duplicate_submissions(self, api_client, vendor_a_user, category):
        """Enforces stable request outcomes by verifying the Idempotency-Key headers."""
        api_client.force_authenticate(user=vendor_a_user)
        url = reverse("product:vendor-product-list")
        idempotency_token = str(uuid.uuid4())
        
        payload = {
            "title": "Unique Tailored Piece",
            "description": "Premium velvet gown",
            "price": "85000.00",
            "category_ids": [category.id],
            "stock_qty": 5,
            "idempotency_key": idempotency_token,
        }
        
        # Request 1: Primary write
        response_1 = api_client.post(
            url, payload, format="json", HTTP_X_IDEMPOTENCY_KEY=idempotency_token
        )
        assert response_1.status_code == status.HTTP_201_CREATED, response_1.content
        
        # Request 2: Duplicate check
        response_2 = api_client.post(
            url, payload, format="json", HTTP_X_IDEMPOTENCY_KEY=idempotency_token
        )
        # Should return cached response with identical created payload
        assert response_2.status_code == status.HTTP_201_CREATED, response_2.content
        assert response_1.json()["data"]["title"] == response_2.json()["data"]["title"]
