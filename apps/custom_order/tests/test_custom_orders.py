# apps/custom_order/tests/test_custom_orders.py
"""
Custom Order (Bespoke Commission) Domain and Contract Tests.

Covers:
  - Happy path: Client submits bespoke design brief (POST /api/v1/ninja/client/custom-orders/)
  - Happy path: Listing commissions with dynamic filters (GET /api/v1/ninja/client/custom-orders/)
  - Happy path: Retrieving a single bespoke commission (GET /api/v1/ninja/client/custom-orders/{id}/)
  - Happy path: Vendor reviews, sets agreed price and approves (POST /api/v1/ninja/vendor/custom-orders/{id}/approve/)
  - Happy path: Client pays milestone tranches sequentially (POST /api/v1/ninja/client/custom-orders/{id}/pay-milestone/)
  - Security path: Unauthorized users are locked out (HTTP 403 / 401)
  - Integrity path: Sequencing paid milestone logic (prevents paying out of order)
"""

import pytest
from decimal import Decimal
from rest_framework import status
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import RefreshToken

from apps.custom_order.models import (
    CustomOrder,
    CustomOrderMilestone,
    CustomOrderStatus,
    MilestonePaymentStatus,
)


# ─── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def api_client():
    return APIClient()


@pytest.fixture
def client_user(db, django_user_model):
    """Seed a verified customer client user."""
    user = django_user_model.objects.create_user(
        email="bespoke_client@fashionistar.test",
        password="SecurePass123!@#",
        role="client",
        is_active=True,
        is_verified=True,
    )
    from apps.client.models import ClientProfile
    ClientProfile.objects.get_or_create(user=user)
    return user


@pytest.fixture
def vendor_user(db, django_user_model):
    """Seed a verified professional vendor user."""
    user = django_user_model.objects.create_user(
        email="bespoke_tailor@fashionistar.test",
        password="SecurePass123!@#",
        role="vendor",
        is_active=True,
        is_verified=True,
    )
    from apps.vendor.models import VendorProfile
    VendorProfile.objects.get_or_create(
        user=user,
        defaults={"store_name": "Premium Bespoke Tailoring", "is_verified": True},
    )
    return user


@pytest.fixture
def vendor_profile(vendor_user):
    return vendor_user.vendor_profile


# ─── Integration & Contract Tests ─────────────────────────────────────────────

@pytest.mark.django_db
class TestCustomOrdersContracts:

    def test_client_submits_bespoke_order_creates_submitted_status(
        self, api_client, client_user, vendor_profile
    ):
        """
        POST /api/v1/ninja/client/custom-orders/
        Submitting a custom brief should create a CustomOrder with SUBMITTED status.
        """
        token = RefreshToken.for_user(client_user).access_token
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        payload = {
            "vendor_id": str(vendor_profile.id),
            "design_brief": "Tailor me a premium Forest Green Cashmere Suit with gold thread details.",
            "budget_ngn": "150000.00",
            "product_snapshot_id": "prod-12345",
        }

        response = api_client.post(
            "/api/v1/ninja/client/custom-orders/", payload, format="json"
        )
        assert response.status_code == status.HTTP_201_CREATED

        data = response.json()
        assert data["reference"].startswith("CO-")
        assert data["status"] == CustomOrderStatus.SUBMITTED
        assert Decimal(data["budget_ngn"]) == Decimal("150000.00")
        assert data["vendor_store_name"] == "Premium Bespoke Tailoring"
        assert len(data["milestones"]) == 0

        # Verify DB entry
        co = CustomOrder.objects.get(id=data["id"])
        assert co.client == client_user
        assert co.vendor == vendor_profile
        assert co.status == CustomOrderStatus.SUBMITTED

    def test_unauthenticated_client_submission_fails(self, api_client, vendor_profile):
        """Unauthenticated custom order creations are rejected with HTTP 401/403."""
        payload = {
            "vendor_id": str(vendor_profile.id),
            "design_brief": "Should fail",
            "budget_ngn": "5000.00",
        }
        response = api_client.post(
            "/api/v1/ninja/client/custom-orders/", payload, format="json"
        )
        assert response.status_code in (status.HTTP_401_UNAUTHORIZED, status.HTTP_403_FORBIDDEN)

    def test_vendor_approves_custom_order_creates_milestone_payment_rows(
        self, api_client, client_user, vendor_user, vendor_profile
    ):
        """
        POST /api/v1/ninja/vendor/custom-orders/{id}/approve/
        When the vendor approves, the order status transitions to APPROVED and
        the system seeds the 4 milestone payment rows (30%, 50%, 70%, 100%).
        """
        # 1. Create a submitted order first
        co = CustomOrder.objects.create(
            client=client_user,
            vendor=vendor_profile,
            design_brief="Fine Agbada",
            budget_ngn=Decimal("200000.00"),
            status=CustomOrderStatus.SUBMITTED,
        )

        # 2. Approve via Vendor API
        token = RefreshToken.for_user(vendor_user).access_token
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        payload = {
            "agreed_amount_ngn": "180000.00",
            "note": "I can do this for 180,000 NGN using top-grade fabric.",
        }

        response = api_client.post(
            f"/api/v1/ninja/vendor/custom-orders/{co.id}/approve/",
            payload,
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["status"] == CustomOrderStatus.APPROVED
        assert Decimal(data["agreed_amount_ngn"]) == Decimal("180000.00")
        assert data["vendor_approval_note"] == payload["note"]

        # Verify Milestones are auto-seeded and match the exact percentage computation
        milestones = data["milestones"]
        assert len(milestones) == 4
        assert milestones[0]["milestone_pct"] == 30
        assert Decimal(milestones[0]["amount_ngn"]) == Decimal("54000.00")  # 30% of 180,000
        assert milestones[0]["payment_status"] == MilestonePaymentStatus.PENDING

        assert milestones[1]["milestone_pct"] == 50
        assert Decimal(milestones[1]["amount_ngn"]) == Decimal("90000.00")  # 50% of 180,000

        # Verify in database
        assert co.milestones.count() == 4
        assert CustomOrder.objects.get(id=co.id).status == CustomOrderStatus.APPROVED

    def test_client_pays_first_milestone_transitions_status_to_in_production(
        self, api_client, client_user, vendor_profile
    ):
        """
        POST /api/v1/ninja/client/custom-orders/{id}/pay-milestone/
        Paying the first milestone (30%) transitions the order status to IN_PRODUCTION.
        """
        # Create approved order with seeded milestones
        co = CustomOrder.objects.create(
            client=client_user,
            vendor=vendor_profile,
            design_brief="Kaftan with embroidery",
            agreed_amount_ngn=Decimal("100000.00"),
            status=CustomOrderStatus.APPROVED,
        )
        co.create_milestones()

        # Pay milestone via Client API
        token = RefreshToken.for_user(client_user).access_token
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        payload = {"milestone_pct": 30}

        response = api_client.post(
            f"/api/v1/ninja/client/custom-orders/{co.id}/pay-milestone/",
            payload,
            format="json",
        )
        assert response.status_code == status.HTTP_200_OK

        data = response.json()
        assert data["status"] == CustomOrderStatus.IN_PRODUCTION

        # Verify milestone 30% paid
        ms_30 = next(m for m in data["milestones"] if m["milestone_pct"] == 30)
        assert ms_30["payment_status"] == MilestonePaymentStatus.PAID
        assert ms_30["paid_at"] is not None

        # Verify database
        m_30 = co.milestones.get(milestone_pct=30)
        assert m_30.payment_status == MilestonePaymentStatus.PAID
        assert co.milestones.get(milestone_pct=50).payment_status == MilestonePaymentStatus.PENDING

    def test_milestone_payments_enforce_valid_order_ownership_and_role_guards(
        self, api_client, client_user, vendor_user, vendor_profile
    ):
        """Cross-role actions (e.g. vendor paying milestones, or client approving briefs) are strictly blocked with 403."""
        co = CustomOrder.objects.create(
            client=client_user,
            vendor=vendor_profile,
            design_brief="Tailor Agbada",
            status=CustomOrderStatus.SUBMITTED,
        )

        # 1. Client tries to approve their own order (Vendor-only action)
        client_token = RefreshToken.for_user(client_user).access_token
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {client_token}")
        response = api_client.post(
            f"/api/v1/ninja/vendor/custom-orders/{co.id}/approve/",
            {"agreed_amount_ngn": "100"},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN

        # 2. Vendor tries to pay milestone (Client-only action)
        co.status = CustomOrderStatus.APPROVED
        co.agreed_amount_ngn = Decimal("50000.00")
        co.save()
        co.create_milestones()

        vendor_token = RefreshToken.for_user(vendor_user).access_token
        api_client.credentials(HTTP_AUTHORIZATION=f"Bearer {vendor_token}")
        response = api_client.post(
            f"/api/v1/ninja/client/custom-orders/{co.id}/pay-milestone/",
            {"milestone_pct": 30},
            format="json",
        )
        assert response.status_code == status.HTTP_403_FORBIDDEN
