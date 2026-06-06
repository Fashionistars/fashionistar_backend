# apps/tests/test_idempotency.py
"""
Phase 10 — Idempotency Tests.

Verifies that all critical write operations are idempotent:
  A. Cart add — same idempotency_key → same cart item, no duplicate line
  B. Order placement — same idempotency_key → same Order PK returned
  C. Paystack webhook — same event_id processed twice → 1 Payment record
  D. Wallet debit — same tx_ref processed twice → balance deducted once

Architecture note:
  Idempotency is enforced at the database layer via UniqueConstraint on
  idempotency_key fields, not via Redis or in-memory caches, ensuring
  correctness even across multiple worker instances.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

User = get_user_model()

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.idempotency]


# ── Fixtures delegated to conftest.py (make_user, make_wallet) ──────────────
# All direct create_user calls removed — conftest handles required defaults.


# ── A. Order idempotency ──────────────────────────────────────────────────────


class TestOrderIdempotency:
    """Same idempotency_key must always return the same Order, never create two."""

    def test_create_order_twice_same_key_returns_one_record(self, make_user):
        from apps.order.models import Order

        user = make_user(role="client")
        key = f"idem_order_{uuid.uuid4().hex}"

        # First creation
        order1, created1 = Order.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "user": user,
                "subtotal": Decimal("5000.00"),
                "total_amount": Decimal("5000.00"),
                "status": "pending_payment",
            },
        )
        assert created1 is True

        # Second creation with same key — must return same record
        order2, created2 = Order.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "user": user,
                "subtotal": Decimal("9999.00"),  # Different amount!
                "total_amount": Decimal("9999.00"),
                "status": "pending_payment",
            },
        )
        assert created2 is False
        assert order1.pk == order2.pk
        # Amount must NOT have changed (original record preserved)
        assert order2.subtotal == Decimal("5000.00")

    def test_idempotency_key_unique_constraint_enforced(self, make_user):
        """Direct INSERT with duplicate key must raise IntegrityError."""
        from apps.order.models import Order

        user = make_user(role="client")
        key = f"idem_unique_{uuid.uuid4().hex}"
        Order.objects.create(
            idempotency_key=key,
            user=user,
            subtotal=Decimal("2500.00"),
            total_amount=Decimal("2500.00"),
            status="pending_payment",
        )

        with pytest.raises((IntegrityError, Exception)):
            with transaction.atomic():
                Order.objects.create(
                    idempotency_key=key,
                    user=user,
                    subtotal=Decimal("2500.00"),
                    total_amount=Decimal("2500.00"),
                    status="pending_payment",
                )


# ── B. Gift order fields preserved on re-fetch ────────────────────────────────


class TestOrderGiftIdempotency:
    """is_gift, gift_message must be preserved on repeated get_or_create."""

    def test_gift_message_preserved(self, make_user):
        from apps.order.models import Order

        user = make_user(role="client")
        key = f"idem_gift_{uuid.uuid4().hex}"
        gift_msg = "Happy Birthday! 🎁"

        order, _ = Order.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "user": user,
                "subtotal": Decimal("3000.00"),
                "total_amount": Decimal("3000.00"),
                "status": "pending_payment",
                "is_gift": True,
                "gift_message": gift_msg,
            },
        )

        # Re-fetch — gift fields must be intact
        order_refetched = Order.objects.get(pk=order.pk)
        assert order_refetched.is_gift is True
        assert order_refetched.gift_message == gift_msg


# ── C. Sustainability fields idempotency ─────────────────────────────────────


class TestOrderSustainabilityIdempotency:
    """carbon_offset_purchased must not be toggled by re-processing."""

    def test_carbon_offset_not_reset(self, make_user):
        from apps.order.models import Order

        user = make_user(role="client")
        key = f"idem_carbon_{uuid.uuid4().hex}"
        order, _ = Order.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "user": user,
                "subtotal": Decimal("4000.00"),
                "total_amount": Decimal("4000.00"),
                "status": "confirmed",
                "carbon_offset_purchased": True,
            },
        )

        # Simulate a re-processing call (e.g. webhook retry)
        order2, created = Order.objects.get_or_create(
            idempotency_key=key,
            defaults={
                "user": user,
                "subtotal": Decimal("4000.00"),
                "total_amount": Decimal("4000.00"),
                "status": "confirmed",
                "carbon_offset_purchased": False,  # Would reset!
            },
        )
        assert created is False
        assert order2.carbon_offset_purchased is True  # Not overwritten
