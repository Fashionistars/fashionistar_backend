from __future__ import annotations

from decimal import Decimal

import pytest
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.authentication.models import UnifiedUser
from apps.client.models import ClientAddress, ClientProfile
from apps.client.serializers.review_serializers import ClientReviewSerializer
from apps.client.services.client_profile_service import ClientProfileService
from apps.product.models import Product, ProductReview, ProductStatus
from apps.wallet.serializers import WalletWithdrawalSerializer


def _auth_client(user: UnifiedUser) -> APIClient:
    client = APIClient()
    client.credentials(
        HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(user).access_token}"
    )
    return client


def _make_client_user(email: str = "client.contract@fashionistar.test") -> UnifiedUser:
    return UnifiedUser.objects.create_user(
        email=email,
        password="Password123!",
        role=UnifiedUser.ROLE_CLIENT,
        is_active=True,
        is_verified=True,
    )


def _make_profile(user: UnifiedUser) -> ClientProfile:
    return ClientProfile.objects.create(
        user=user,
        bio="Contract test profile",
        default_shipping_address="",
        state="Lagos",
        country="Nigeria",
        preferred_size="M",
        style_preferences=["casual"],
        favourite_colours=["black"],
    )


@pytest.mark.django_db
def test_add_address_writes_through_client_profile_relation():
    user = _make_client_user()
    profile = _make_profile(user)

    address = ClientProfileService.add_address(
        user=user,
        address_data={
            "label": "Home",
            "full_name": "Client Example",
            "phone": "+2348012345678",
            "street_address": "12 Okigwe Street",
            "city": "Ikeja",
            "state": "Lagos",
            "country": "Nigeria",
            "postal_code": "100271",
            "is_default": True,
        },
    )

    assert address.client_id == profile.pk
    assert profile.client_addresses.filter(pk=address.pk).exists()


@pytest.mark.django_db
def test_set_default_address_updates_profile_shipping_shortcut():
    user = _make_client_user("client.default@fashionistar.test")
    profile = _make_profile(user)
    first = ClientAddress.objects.create(
        client=profile,
        label="Home",
        full_name="Client Example",
        phone="+2348012345678",
        street_address="12 Okigwe Street",
        city="Ikeja",
        state="Lagos",
        country="Nigeria",
        postal_code="100271",
        is_default=False,
    )
    second = ClientAddress.objects.create(
        client=profile,
        label="Office",
        full_name="Client Example",
        phone="+2348012345678",
        street_address="9 Adeola Odeku",
        city="Victoria Island",
        state="Lagos",
        country="Nigeria",
        postal_code="101241",
        is_default=False,
    )

    result = ClientProfileService.set_default_address(user=user, address_id=second.pk)
    profile.refresh_from_db()
    first.refresh_from_db()
    second.refresh_from_db()

    assert result.pk == second.pk
    assert second.is_default is True
    assert first.is_default is False
    assert profile.default_shipping_address == "9 Adeola Odeku"


@pytest.mark.django_db
def test_client_review_serializer_persists_product_review():
    user = _make_client_user("client.review@fashionistar.test")
    product = Product.objects.create(
        title="Reviewable Kaftan",
        slug="reviewable-kaftan",
        description="A premium kaftan ready for reviews.",
        price=Decimal("15000.00"),
        currency="NGN",
        stock_qty=5,
        in_stock=True,
        status=ProductStatus.PUBLISHED,
        condition="new",
    )

    serializer = ClientReviewSerializer(
        data={
            "product_id": str(product.pk),
            "rating": 5,
            "review": "Excellent fit and finishing.",
        },
        context={"request": type("Request", (), {"user": user})()},
    )

    assert serializer.is_valid(), serializer.errors
    review = serializer.save()

    assert ProductReview.objects.filter(pk=review.pk, user=user, product=product).exists()


@pytest.mark.django_db
def test_client_review_create_endpoint_persists_review():
    user = _make_client_user("client.review.endpoint@fashionistar.test")
    product = Product.objects.create(
        title="Review Endpoint Agbada",
        slug="review-endpoint-agbada",
        description="An agbada used for endpoint contract testing.",
        price=Decimal("45000.00"),
        currency="NGN",
        stock_qty=3,
        in_stock=True,
        status=ProductStatus.PUBLISHED,
        condition="new",
    )

    response = _auth_client(user).post(
        "/api/v1/client/reviews/create/",
        {
            "product_id": str(product.pk),
            "rating": 4,
            "review": "Very clean stitching and fabric quality.",
        },
        format="json",
    )

    assert response.status_code == 201
    assert ProductReview.objects.filter(user=user, product=product).count() == 1


def test_wallet_withdrawal_serializer_enforces_platform_minimum():
    serializer = WalletWithdrawalSerializer(
        data={
            "amount": "999.99",
            "pin": "1234",
            "bank_code": "044",
            "account_number": "0123456789",
            "account_name": "Client Example",
        }
    )

    assert serializer.is_valid() is False
    assert "amount" in serializer.errors


@pytest.mark.django_db
def test_shared_order_views_reject_vendor_role_for_client_order_history():
    user = UnifiedUser.objects.create_user(
        email="vendor.orders.blocked@fashionistar.test",
        password="Password123!",
        role=UnifiedUser.ROLE_VENDOR,
        is_active=True,
        is_verified=True,
    )

    response = _auth_client(user).get("/api/v1/orders/")

    assert response.status_code == 403
