# apps/tests/test_wallet_service.py
"""
Phase 10 — WalletService Unit Tests.

Verifies the complete wallet debit/credit/escrow lifecycle:
  A. Credit — balance increases, WalletTransaction created
  B. Debit — balance decreases, insufficient balance raises ValueError
  C. Hold — held_balance increases, available_balance decreases
  D. Release hold — held_balance decreases, available_balance restored
  E. Idempotency — same tx_ref cannot be processed twice (IntegrityError)
  F. Race conditions — concurrent debits respect select_for_update locking
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction

User = get_user_model()

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.wallet]


# ── Fixtures ──────────────────────────────────────────────────────────────────


@pytest.fixture
def wallet_user(db):
    """Create a vendor user with a Wallet seeded to ₦50,000."""
    from apps.wallet.models import Wallet
    user = User.objects.create_user(
        email=f"wallet_{uuid.uuid4().hex[:8]}@fashionistar.ng",
        password="Wallet!2026",
        is_active=True,
        is_verified=True,
        role="vendor",
    )
    Wallet.objects.create(
        user=user,
        available_balance=Decimal("50000.00"),
        held_balance=Decimal("0.00"),
        total_credited=Decimal("50000.00"),
        total_debited=Decimal("0.00"),
        currency="NGN",
    )
    return user


# ── A. Credit ─────────────────────────────────────────────────────────────────


class TestWalletCredit:
    """Credit increases available_balance and creates a WalletTransaction."""

    def test_credit_increases_balance(self, wallet_user, db):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        WalletService.credit(
            user=wallet_user,
            amount=Decimal("10000.00"),
            description="Test credit",
            reference=f"ref_credit_{uuid.uuid4().hex}",
        )

        wallet = Wallet.objects.get(user=wallet_user)
        assert wallet.available_balance == Decimal("60000.00")
        assert wallet.total_credited >= Decimal("60000.00")

    def test_credit_creates_transaction_record(self, wallet_user, db):
        from apps.wallet.models import WalletTransaction
        from apps.wallet.services.wallet_service import WalletService

        ref = f"ref_tx_{uuid.uuid4().hex}"
        WalletService.credit(
            user=wallet_user,
            amount=Decimal("5000.00"),
            description="Order payment received",
            reference=ref,
        )

        tx = WalletTransaction.objects.get(reference=ref)
        assert tx.transaction_type == "credit"
        assert tx.amount == Decimal("5000.00")
        assert tx.user == wallet_user


# ── B. Debit ──────────────────────────────────────────────────────────────────


class TestWalletDebit:
    """Debit decreases balance; raises ValueError when insufficient."""

    def test_debit_decreases_balance(self, wallet_user, db):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        WalletService.debit(
            user=wallet_user,
            amount=Decimal("20000.00"),
            description="Payout",
            reference=f"ref_debit_{uuid.uuid4().hex}",
        )

        wallet = Wallet.objects.get(user=wallet_user)
        assert wallet.available_balance == Decimal("30000.00")

    def test_debit_raises_on_insufficient_balance(self, wallet_user, db):
        from apps.wallet.services.wallet_service import WalletService

        with pytest.raises(ValueError, match="Insufficient"):
            WalletService.debit(
                user=wallet_user,
                amount=Decimal("999999.00"),  # More than available
                description="Overspend attempt",
                reference=f"ref_over_{uuid.uuid4().hex}",
            )

    def test_debit_insufficient_does_not_modify_balance(self, wallet_user, db):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        original = Wallet.objects.get(user=wallet_user).available_balance

        try:
            WalletService.debit(
                user=wallet_user,
                amount=Decimal("999999.00"),
                description="Should fail",
                reference=f"ref_fail_{uuid.uuid4().hex}",
            )
        except ValueError:
            pass

        wallet = Wallet.objects.get(user=wallet_user)
        assert wallet.available_balance == original  # Not modified


# ── C. Hold (Escrow) ──────────────────────────────────────────────────────────


class TestWalletHold:
    """Hold moves amount from available to held."""

    def test_hold_transfers_between_buckets(self, wallet_user, db):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        WalletService.hold(
            user=wallet_user,
            amount=Decimal("15000.00"),
            reference=f"hold_{uuid.uuid4().hex}",
        )

        wallet = Wallet.objects.get(user=wallet_user)
        assert wallet.held_balance == Decimal("15000.00")
        assert wallet.available_balance == Decimal("35000.00")

    def test_hold_raises_on_insufficient(self, wallet_user, db):
        from apps.wallet.services.wallet_service import WalletService

        with pytest.raises(ValueError):
            WalletService.hold(
                user=wallet_user,
                amount=Decimal("999999.00"),
                reference=f"hold_fail_{uuid.uuid4().hex}",
            )


# ── D. Release ────────────────────────────────────────────────────────────────


class TestWalletRelease:
    """Release returns held amount back to available."""

    def test_release_restores_available_balance(self, wallet_user, db):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        ref = f"hold_{uuid.uuid4().hex}"
        WalletService.hold(user=wallet_user, amount=Decimal("10000.00"), reference=ref)
        WalletService.release_hold(user=wallet_user, amount=Decimal("10000.00"), reference=ref)

        wallet = Wallet.objects.get(user=wallet_user)
        assert wallet.held_balance == Decimal("0.00")
        assert wallet.available_balance == Decimal("50000.00")


# ── E. Idempotency ────────────────────────────────────────────────────────────


class TestWalletIdempotency:
    """Same reference must not create duplicate WalletTransactions."""

    def test_duplicate_reference_raises(self, wallet_user, db):
        from apps.wallet.services.wallet_service import WalletService

        ref = f"idem_{uuid.uuid4().hex}"
        WalletService.credit(
            user=wallet_user,
            amount=Decimal("1000.00"),
            description="First credit",
            reference=ref,
        )

        with pytest.raises((IntegrityError, ValueError)):
            with transaction.atomic():
                WalletService.credit(
                    user=wallet_user,
                    amount=Decimal("1000.00"),
                    description="Duplicate credit",
                    reference=ref,
                )


# ── F. Concurrency ────────────────────────────────────────────────────────────


class TestWalletConcurrency:
    """10 concurrent debits of ₦1,000 must not overdraft a ₦5,000 account."""

    def test_concurrent_debits_respect_locking(self, db):
        """Only 5 debits should succeed on a ₦5,000 wallet."""
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        # Seed a fresh user with ₦5,000
        user = User.objects.create_user(
            email=f"concurrent_{uuid.uuid4().hex}@fashionistar.ng",
            password="Concurrent!2026",
            is_active=True,
            is_verified=True,
        )
        Wallet.objects.create(
            user=user,
            available_balance=Decimal("5000.00"),
            held_balance=Decimal("0.00"),
            total_credited=Decimal("5000.00"),
            total_debited=Decimal("0.00"),
            currency="NGN",
        )

        successes = 0
        failures = 0

        def attempt_debit(i: int):
            try:
                WalletService.debit(
                    user=user,
                    amount=Decimal("1000.00"),
                    description=f"Concurrent debit #{i}",
                    reference=f"concurrent_{uuid.uuid4().hex}",
                )
                return "success"
            except (ValueError, Exception):
                return "failure"

        with ThreadPoolExecutor(max_workers=10) as executor:
            futures = [executor.submit(attempt_debit, i) for i in range(10)]
            results = [f.result() for f in as_completed(futures)]

        successes = results.count("success")
        failures = results.count("failure")

        # Exactly 5 debits of ₦1,000 should succeed against a ₦5,000 balance
        assert successes == 5, f"Expected 5 successes, got {successes}"
        assert failures == 5, f"Expected 5 failures, got {failures}"

        # Final balance must be exactly ₦0 — no overdraft
        wallet = Wallet.objects.get(user=user)
        assert wallet.available_balance == Decimal("0.00"), \
            f"Expected ₦0.00, got ₦{wallet.available_balance}"
