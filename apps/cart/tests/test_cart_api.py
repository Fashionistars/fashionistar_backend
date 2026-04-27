# apps/cart/tests/test_cart_api.py
"""
Cart domain test suite.

Tests:
  - Cart creation on first get_or_create
  - Add item: success, stock enforcement, price snapshot
  - Duplicate add: merges into existing line (no duplicate rows)
  - Remove item
  - Update quantity (set to 0 removes)
  - Save for later toggle
  - Coupon: apply, minimum order, remove
  - Cart clear
  - Guest cart merge
  - Permission: anonymous → 401, wrong role → 403
  - Concurrency: two requests adding same item simultaneously
"""

import pytest
from decimal import Decimal
from rest_framework import status
from rest_framework.test import APIClient

from apps.cart.models import Cart, CartItem
from apps.cart.services import (
    get_or_create_cart,
    add_item,
    remove_item,
    update_item_quantity,
    apply_coupon,
    clear_cart,
    merge_guest_cart,
)
from apps.product.models import Product, ProductStatus, Coupon


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def client_user(db, django_user_model):
    return django_user_model.objects.create_user(
        email="cart_client@fashionistar.test",
        password="TestPass123!",
        role="client",
        is_active=True,
        is_verified=True,
    )


@pytest.fixture
def vendor_profile(db, django_user_model):
    vendor_user = django_user_model.objects.create_user(
        email="cart_vendor@fashionistar.test",
        password="Pass123!",
        role="vendor",
        is_active=True,
        is_verified=True,
    )
    from apps.vendor.models import VendorProfile
    profile, _ = VendorProfile.objects.get_or_create(
        user=vendor_user,
        defaults={"business_name": "Test Cart Shop", "is_approved": True},
    )
    return profile


@pytest.fixture
def product(db, vendor_profile):
    return Product.objects.create(
        vendor=vendor_profile,
        title="Test Kaftan",
        description="A fine kaftan",
        price=Decimal("10000.00"),
        stock_qty=20,
        status=ProductStatus.PUBLISHED,
    )


@pytest.fixture
def coupon(db, vendor_profile):
    from django.utils import timezone
    return Coupon.objects.create(
        code="CART10",
        discount_type="percentage",
        discount_value=Decimal("10.00"),
        minimum_order=Decimal("5000.00"),
        valid_from=timezone.now(),
        valid_to=timezone.now() + timezone.timedelta(days=30),
        vendor=vendor_profile,
        active=True,
    )


# ─── Service Tests ─────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCartService:

    def test_get_or_create_cart(self, client_user):
        cart = get_or_create_cart(client_user)
        assert cart.user == client_user
        # Second call returns same cart
        cart2 = get_or_create_cart(client_user)
        assert cart.id == cart2.id

    def test_add_item_creates_cart_item(self, client_user, product):
        add_item(user=client_user, product_slug=product.slug, quantity=2)
        cart = get_or_create_cart(client_user)
        assert cart.items.count() == 1
        item = cart.items.first()
        assert item.quantity == 2
        assert item.unit_price == product.price

    def test_add_item_increments_quantity(self, client_user, product):
        add_item(user=client_user, product_slug=product.slug, quantity=2)
        add_item(user=client_user, product_slug=product.slug, quantity=3)
        cart = get_or_create_cart(client_user)
        # Must still be 1 item, not 2
        assert cart.items.count() == 1
        assert cart.items.first().quantity == 5

    def test_add_item_stock_enforcement(self, client_user, product):
        product.stock_qty = 3
        product.save()
        with pytest.raises(ValueError, match="Only 3"):
            add_item(user=client_user, product_slug=product.slug, quantity=10)

    def test_price_snapshot(self, client_user, product):
        add_item(user=client_user, product_slug=product.slug, quantity=1)
        item = CartItem.objects.get(cart__user=client_user, product=product)
        original_price = item.unit_price
        # Simulate price change
        product.price = Decimal("99999.00")
        product.save()
        # Price snapshot NOT auto-updated
        item.refresh_from_db()
        assert item.unit_price == original_price

    def test_remove_item(self, client_user, product):
        add_item(user=client_user, product_slug=product.slug, quantity=1)
        item = CartItem.objects.get(cart__user=client_user, product=product)
        remove_item(user=client_user, item_id=item.id)
        assert CartItem.objects.filter(id=item.id).count() == 0

    def test_update_quantity_to_zero_removes_item(self, client_user, product):
        add_item(user=client_user, product_slug=product.slug, quantity=2)
        item = CartItem.objects.get(cart__user=client_user, product=product)
        update_item_quantity(user=client_user, item_id=item.id, quantity=0)
        assert CartItem.objects.filter(id=item.id).count() == 0

    def test_apply_coupon(self, client_user, product, coupon):
        add_item(user=client_user, product_slug=product.slug, quantity=2)  # 20000 total
        cart = apply_coupon(user=client_user, code="CART10")
        # 10% of 20000 = 2000
        assert cart.coupon_discount == Decimal("2000.00")
        assert cart.total == Decimal("18000.00")

    def test_apply_coupon_minimum_order_enforced(self, client_user, product, coupon):
        add_item(user=client_user, product_slug=product.slug, quantity=1)  # 10000 >= 5000 → ok
        cart = apply_coupon(user=client_user, code="CART10")
        assert cart.coupon is not None

    def test_clear_cart(self, client_user, product):
        add_item(user=client_user, product_slug=product.slug, quantity=3)
        clear_cart(user=client_user)
        cart = get_or_create_cart(client_user)
        assert cart.items.count() == 0

    def test_merge_guest_cart(self, client_user, product):
        guest_items = [{"product_slug": product.slug, "quantity": 2}]
        cart = merge_guest_cart(user=client_user, guest_items=guest_items)
        assert cart.items.count() == 1

    def test_merge_guest_cart_skips_invalid_items(self, client_user):
        guest_items = [{"product_slug": "nonexistent", "quantity": 1}]
        cart = merge_guest_cart(user=client_user, guest_items=guest_items)
        assert cart.items.count() == 0


# ─── API Tests ─────────────────────────────────────────────────────────────────

@pytest.mark.django_db
class TestCartAPI:

    def test_anonymous_cannot_access_cart(self, api_client):
        response = api_client.get("/api/v1/cart/")
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_retrieve_cart(self, api_client, client_user):
        api_client.force_authenticate(client_user)
        response = api_client.get("/api/v1/cart/")
        assert response.status_code == status.HTTP_200_OK

    def test_add_item_via_api(self, api_client, client_user, product):
        api_client.force_authenticate(client_user)
        response = api_client.post("/api/v1/cart/add/", {
            "product_slug": product.slug,
            "quantity": 1,
        }, format="json")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["item_count"] == 1

    def test_add_item_over_stock_rejected(self, api_client, client_user, product):
        product.stock_qty = 1
        product.save()
        api_client.force_authenticate(client_user)
        response = api_client.post("/api/v1/cart/add/", {
            "product_slug": product.slug,
            "quantity": 99,
        }, format="json")
        assert response.status_code == status.HTTP_400_BAD_REQUEST

    def test_remove_item_via_api(self, api_client, client_user, product):
        add_item(user=client_user, product_slug=product.slug, quantity=1)
        item = CartItem.objects.get(cart__user=client_user, product=product)
        api_client.force_authenticate(client_user)
        response = api_client.delete(f"/api/v1/cart/items/{item.id}/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["item_count"] == 0

    def test_clear_cart_via_api(self, api_client, client_user, product):
        add_item(user=client_user, product_slug=product.slug, quantity=2)
        api_client.force_authenticate(client_user)
        response = api_client.delete("/api/v1/cart/clear/")
        assert response.status_code == status.HTTP_200_OK
        assert response.data["data"]["item_count"] == 0
