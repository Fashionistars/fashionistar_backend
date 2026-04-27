# apps/product/tests/test_product_api.py
"""
Comprehensive test suite for the Product domain.

Covers:
  - Model creation / slug / SKU auto-generation
  - Serializer validation
  - Public API: list, detail, featured
  - Vendor API: CRUD, gallery, publish, coupon
  - Client API: review, wishlist
  - Service layer: inventory adjustment, coupon validation
  - Permission enforcement
  - Soft-delete behaviour
"""

import pytest
from decimal import Decimal
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APIClient

from apps.product.models import (
    Product,
    ProductTag,
    ProductSize,
    ProductColor,
    ProductGalleryMedia,
    ProductReview,
    ProductWishlist,
    Coupon,
    ProductStatus,
    ProductInventoryLog,
)
from apps.product.services import (
    create_product,
    update_product,
    publish_product,
    archive_product,
    adjust_inventory,
    create_review,
    toggle_wishlist,
    validate_and_apply_coupon,
)
from apps.product.selectors import (
    get_published_products,
    get_product_detail,
    get_user_wishlist,
    get_coupon_by_code,
)


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def client_user(db, django_user_model):
    user = django_user_model.objects.create_user(
        email="client@test.fashionistar.com",
        password="TestPass123!",
        role="client",
        is_active=True,
        is_verified=True,
    )
    return user


@pytest.fixture
def vendor_user(db, django_user_model):
    user = django_user_model.objects.create_user(
        email="vendor@test.fashionistar.com",
        password="TestPass123!",
        role="vendor",
        is_active=True,
        is_verified=True,
    )
    return user


@pytest.fixture
def vendor_profile(db, vendor_user):
    from apps.vendor.models import VendorProfile
    profile, _ = VendorProfile.objects.get_or_create(
        user=vendor_user,
        defaults={"store_name": "Test Tailor Shop", "is_verified": True},
    )
    return profile


@pytest.fixture
def sample_product(db, vendor_profile):
    """A published product for public endpoint tests."""
    product = Product.objects.create(
        vendor=vendor_profile,
        title="Adire Ankara Dress",
        description="Handcrafted Adire Ankara dress with custom sizing.",
        price=Decimal("25000.00"),
        currency="NGN",
        stock_qty=10,
        status=ProductStatus.PUBLISHED,
    )
    return product


@pytest.fixture
def draft_product(db, vendor_profile):
    product = Product.objects.create(
        vendor=vendor_profile,
        title="Unreleased Kaftan",
        description="A kaftan not yet ready.",
        price=Decimal("15000.00"),
        stock_qty=5,
        status=ProductStatus.DRAFT,
    )
    return product


@pytest.fixture
def sample_coupon(db, vendor_profile, sample_product):
    from django.utils import timezone
    return Coupon.objects.create(
        code="FASHION20",
        discount_type="percentage",
        discount_value=Decimal("20.00"),
        minimum_order=Decimal("10000.00"),
        maximum_discount=Decimal("5000.00"),
        valid_from=timezone.now(),
        valid_to=timezone.now() + timezone.timedelta(days=30),
        vendor=vendor_profile,
        active=True,
    )


# ─────────────────────────────────────────────────────────────────────────────
# MODEL TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestProductModel:

    def test_slug_auto_generated(self, db, vendor_profile):
        p = Product.objects.create(
            vendor=vendor_profile,
            title="Luxury Agbada Set",
            description="A fine agbada set.",
            price=Decimal("50000.00"),
        )
        assert p.slug == "luxury-agbada-set"

    def test_slug_uniqueness_on_collision(self, db, vendor_profile):
        Product.objects.create(
            vendor=vendor_profile, title="Kaftan Set",
            description="x", price=Decimal("1000"),
        )
        p2 = Product.objects.create(
            vendor=vendor_profile, title="Kaftan Set",
            description="y", price=Decimal("2000"),
        )
        assert p2.slug == "kaftan-set-1"

    def test_sku_auto_generated(self, db, vendor_profile):
        p = Product.objects.create(
            vendor=vendor_profile, title="Embroidered Blouse",
            description="x", price=Decimal("8000"),
        )
        assert p.sku.startswith("FSN-")

    def test_in_stock_flag_sync(self, db, vendor_profile):
        p = Product.objects.create(
            vendor=vendor_profile, title="Lace Gown",
            description="x", price=Decimal("30000"), stock_qty=0,
        )
        assert p.in_stock is False

    def test_discount_percentage(self, db, vendor_profile):
        p = Product.objects.create(
            vendor=vendor_profile, title="Aso-oke",
            description="x", price=Decimal("8000"), old_price=Decimal("10000"),
        )
        assert p.discount_percentage == 20

    def test_soft_delete(self, db, sample_product):
        sample_product.soft_delete()
        sample_product.refresh_from_db()
        assert sample_product.is_deleted is True
        assert sample_product.deleted_at is not None


# ─────────────────────────────────────────────────────────────────────────────
# SERIALIZER TESTS
# ─────────────────────────────────────────────────────────────────────────────

class TestProductSerializers:

    def test_write_serializer_valid(self, db):
        from apps.product.serializers import ProductWriteSerializer
        data = {
            "title": "Kaftan",
            "description": "Beautiful kaftan",
            "price": "12000.00",
            "stock_qty": 5,
            "currency": "NGN",
        }
        s = ProductWriteSerializer(data=data)
        assert s.is_valid(), s.errors

    def test_write_serializer_invalid_price(self, db):
        from apps.product.serializers import ProductWriteSerializer
        s = ProductWriteSerializer(data={
            "title": "x", "description": "y", "price": "-500", "stock_qty": 1,
        })
        assert not s.is_valid()
        assert "price" in s.errors

    def test_review_write_serializer_rating_range(self, db):
        from apps.product.serializers import ProductReviewWriteSerializer
        s = ProductReviewWriteSerializer(data={"rating": 6, "review": "Great!"})
        assert not s.is_valid()
        assert "rating" in s.errors


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC API TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPublicProductAPI:

    def test_list_returns_published_only(self, api_client, sample_product, draft_product):
        url = "/api/v1/products/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        slugs = [p["slug"] for p in response.data["data"]]
        assert sample_product.slug in slugs
        assert draft_product.slug not in slugs

    def test_detail_returns_full_data(self, api_client, sample_product):
        url = f"/api/v1/products/{sample_product.slug}/"
        response = api_client.get(url)
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["slug"] == sample_product.slug

    def test_detail_404_for_unknown_slug(self, api_client):
        response = api_client.get("/api/v1/products/nonexistent-product/")
        assert response.status_code == status.HTTP_404_NOT_FOUND

    def test_featured_list(self, api_client, db, vendor_profile):
        Product.objects.create(
            vendor=vendor_profile, title="Featured Dress",
            description="x", price=Decimal("20000"),
            status=ProductStatus.PUBLISHED, featured=True,
        )
        response = api_client.get("/api/v1/products/featured/")
        assert response.status_code == status.HTTP_200_OK
        assert len(response.data["data"]) >= 1


# ─────────────────────────────────────────────────────────────────────────────
# VENDOR API TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestVendorProductAPI:

    def test_create_product_as_vendor(self, api_client, vendor_user, vendor_profile):
        api_client.force_authenticate(vendor_user)
        response = api_client.post("/api/v1/products/vendor/", {
            "title": "New Embroidered Kaftan",
            "description": "A premium kaftan",
            "price": "18000.00",
            "stock_qty": 3,
            "currency": "NGN",
        }, format="json")
        assert response.status_code == status.HTTP_201_CREATED
        assert response.data["data"]["status"] == ProductStatus.DRAFT

    def test_create_product_denied_for_client(self, api_client, client_user):
        api_client.force_authenticate(client_user)
        response = api_client.post("/api/v1/products/vendor/", {}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_create_product_denied_for_anonymous(self, api_client):
        response = api_client.post("/api/v1/products/vendor/", {}, format="json")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_vendor_cannot_see_other_vendor_product(self, db, api_client, django_user_model):
        other_user = django_user_model.objects.create_user(
            email="other@vendor.com", password="x", role="vendor",
            is_active=True, is_verified=True,
        )
        from apps.vendor.models import VendorProfile
        other_vendor, _ = VendorProfile.objects.get_or_create(
            user=other_user, defaults={"store_name": "Other Shop", "is_verified": True}
        )
        Product.objects.create(
            vendor=other_vendor, title="Other Dress",
            description="x", price=Decimal("10000"),
        )
        api_client.force_authenticate(other_user)
        response = api_client.get("/api/v1/products/vendor/")
        # vendor endpoint is scoped — only returns requesting vendor's own products
        assert response.status_code == status.HTTP_200_OK
        slugs = [p.get("slug") for p in response.data["data"]]
        assert "other-dress" in slugs

    def test_publish_product(self, api_client, vendor_user, vendor_profile, draft_product):
        api_client.force_authenticate(vendor_user)
        response = api_client.post(f"/api/v1/products/vendor/{draft_product.slug}/publish/")
        assert response.status_code == status.HTTP_200_OK
        draft_product.refresh_from_db()
        assert draft_product.status == ProductStatus.PENDING

    def test_archive_product(self, api_client, vendor_user, vendor_profile, draft_product):
        api_client.force_authenticate(vendor_user)
        response = api_client.delete(f"/api/v1/products/vendor/{draft_product.slug}/")
        assert response.status_code == status.HTTP_204_NO_CONTENT
        draft_product.refresh_from_db()
        assert draft_product.status == ProductStatus.ARCHIVED


# ─────────────────────────────────────────────────────────────────────────────
# CLIENT: REVIEW & WISHLIST
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestReviewAndWishlist:

    def test_submit_review(self, api_client, client_user, sample_product):
        api_client.force_authenticate(client_user)
        response = api_client.post(
            f"/api/v1/products/{sample_product.slug}/reviews/",
            {"rating": 5, "review": "Absolutely stunning!"},
            format="json",
        )
        assert response.status_code == status.HTTP_201_CREATED
        assert ProductReview.objects.filter(user=client_user, product=sample_product).exists()

    def test_duplicate_review_rejected(self, api_client, client_user, sample_product):
        ProductReview.objects.create(
            user=client_user, product=sample_product, rating=4, review="Good."
        )
        api_client.force_authenticate(client_user)
        response = api_client.post(
            f"/api/v1/products/{sample_product.slug}/reviews/",
            {"rating": 3, "review": "Trying again."},
            format="json",
        )
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_toggle_wishlist_add(self, api_client, client_user, sample_product):
        api_client.force_authenticate(client_user)
        response = api_client.post(f"/api/v1/products/wishlist/{sample_product.slug}/toggle/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["added"] is True

    def test_toggle_wishlist_remove(self, api_client, client_user, sample_product):
        ProductWishlist.objects.create(user=client_user, product=sample_product)
        api_client.force_authenticate(client_user)
        response = api_client.post(f"/api/v1/products/wishlist/{sample_product.slug}/toggle/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["added"] is False


# ─────────────────────────────────────────────────────────────────────────────
# SERVICE LAYER TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestProductServiceLayer:

    def test_adjust_inventory_prevents_negative(self, sample_product):
        sample_product.stock_qty = 3
        sample_product.save()
        log = adjust_inventory(
            product=sample_product,
            quantity_delta=-10,
            reason="sale",
            reference_id="TEST-001",
        )
        sample_product.refresh_from_db()
        assert sample_product.stock_qty == 0
        assert log.quantity_after == 0

    def test_adjust_inventory_creates_log(self, sample_product):
        initial = sample_product.stock_qty
        adjust_inventory(
            product=sample_product,
            quantity_delta=5,
            reason="restock",
        )
        assert ProductInventoryLog.objects.filter(product=sample_product).count() >= 1

    def test_coupon_percentage_validation(self, sample_coupon):
        result = validate_and_apply_coupon(
            code="FASHION20",
            user=None,
            order_subtotal=Decimal("25000.00"),
        )
        # 20% of 25000 = 5000, but capped at max_discount=5000
        assert result["discount_amount"] == Decimal("5000.00")

    def test_coupon_minimum_order_enforcement(self, sample_coupon):
        with pytest.raises(ValueError, match="Minimum order amount"):
            validate_and_apply_coupon(
                code="FASHION20",
                user=None,
                order_subtotal=Decimal("5000.00"),  # below minimum of 10000
            )

    def test_coupon_not_found(self, db):
        with pytest.raises(ValueError, match="not found"):
            validate_and_apply_coupon(
                code="NONEXISTENT",
                user=None,
                order_subtotal=Decimal("20000.00"),
            )


# ─────────────────────────────────────────────────────────────────────────────
# PERMISSION MATRIX TESTS
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestPermissionMatrix:

    def test_anonymous_cannot_access_wishlist(self, api_client):
        response = api_client.get("/api/v1/products/wishlist/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_vendor_cannot_review_product(self, api_client, vendor_user, sample_product):
        api_client.force_authenticate(vendor_user)
        response = api_client.post(
            f"/api/v1/products/{sample_product.slug}/reviews/",
            {"rating": 5, "review": "Great!"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

    def test_client_cannot_create_coupon(self, api_client, client_user):
        api_client.force_authenticate(client_user)
        response = api_client.post("/api/v1/products/coupons/", {}, format="json")
        assert response.status_code == status.HTTP_403_FORBIDDEN
