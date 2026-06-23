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

All user creation is delegated to conftest.make_user / conftest.make_wallet
which correctly sets objected_processing_purposes=[] and all required defaults.
"""

from __future__ import annotations

import uuid
from decimal import Decimal
from concurrent.futures import ThreadPoolExecutor, as_completed

import pytest
from django.db import IntegrityError, transaction

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.wallet]


# ── A. Credit ─────────────────────────────────────────────────────────────────


class TestWalletCredit:
    """Credit increases available_balance and creates a WalletTransaction."""

    def test_credit_increases_balance(self, make_user, make_wallet):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("50000.00"))

        WalletService.credit(
            user=user,
            amount=Decimal("10000.00"),
            description="Test credit",
            reference=f"ref_credit_{uuid.uuid4().hex}",
        )

        wallet = Wallet.objects.get(user=user)
        assert wallet.available_balance == Decimal("60000.00")
        assert wallet.total_credited >= Decimal("60000.00")

    def test_credit_creates_transaction_record(self, make_user, make_wallet):
        from apps.wallet.models import WalletTransaction
        from apps.wallet.services.wallet_service import WalletService

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("50000.00"))

        ref = f"ref_tx_{uuid.uuid4().hex}"
        WalletService.credit(
            user=user,
            amount=Decimal("5000.00"),
            description="Order payment received",
            reference=ref,
        )

        tx = WalletTransaction.objects.get(reference=ref)
        assert tx.entry_type == "credit"
        assert tx.amount == Decimal("5000.00")
        assert tx.wallet.user == user


# ── B. Debit ──────────────────────────────────────────────────────────────────


class TestWalletDebit:
    """Debit decreases balance; raises ValueError when insufficient."""

    def test_debit_decreases_balance(self, make_user, make_wallet):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("50000.00"))

        WalletService.debit(
            user=user,
            amount=Decimal("20000.00"),
            description="Payout",
            reference=f"ref_debit_{uuid.uuid4().hex}",
        )

        wallet = Wallet.objects.get(user=user)
        assert wallet.available_balance == Decimal("30000.00")

    def test_debit_raises_on_insufficient_balance(self, make_user, make_wallet):
        from apps.wallet.services.wallet_service import WalletService

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("50000.00"))

        with pytest.raises(ValueError, match="Insufficient"):
            WalletService.debit(
                user=user,
                amount=Decimal("999999.00"),
                description="Overspend attempt",
                reference=f"ref_over_{uuid.uuid4().hex}",
            )

    def test_debit_insufficient_does_not_modify_balance(self, make_user, make_wallet):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("50000.00"))
        original = Wallet.objects.get(user=user).available_balance

        try:
            WalletService.debit(
                user=user,
                amount=Decimal("999999.00"),
                description="Should fail",
                reference=f"ref_fail_{uuid.uuid4().hex}",
            )
        except ValueError:
            pass

        wallet = Wallet.objects.get(user=user)
        assert wallet.available_balance == original  # Not modified


# ── C. Hold (Escrow) ──────────────────────────────────────────────────────────


class TestWalletHold:
    """Hold moves amount from available to held."""

    def test_hold_transfers_between_buckets(self, make_user, make_wallet):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("50000.00"))

        WalletService.escrow_hold(
            user=user,
            amount=Decimal("15000.00"),
            order_reference=f"hold_{uuid.uuid4().hex}",
        )

        wallet = Wallet.objects.get(user=user)
        assert wallet.escrow_balance == Decimal("15000.00")
        assert wallet.available_balance == Decimal("35000.00")

    def test_hold_raises_on_insufficient(self, make_user, make_wallet):
        from apps.wallet.services.wallet_service import WalletService

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("50000.00"))

        with pytest.raises(ValueError):
            WalletService.escrow_hold(
                user=user,
                amount=Decimal("999999.00"),
                order_reference=f"hold_fail_{uuid.uuid4().hex}",
            )


# ── D. Release ────────────────────────────────────────────────────────────────


class TestWalletRelease:
    """Release returns held amount back to available."""

    def test_release_restores_available_balance(self, make_user, make_wallet):
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("50000.00"))

        ref = f"hold_{uuid.uuid4().hex}"
        WalletService.escrow_hold(user=user, amount=Decimal("10000.00"), order_reference=ref)
        WalletService.escrow_refund(buyer_user=user, amount=Decimal("10000.00"), order_reference=ref)

        wallet = Wallet.objects.get(user=user)
        assert wallet.escrow_balance == Decimal("0.00")
        assert wallet.available_balance == Decimal("60000.00")


# ── E. Idempotency ────────────────────────────────────────────────────────────


class TestWalletIdempotency:
    """Same reference must not create duplicate WalletTransactions."""

    def test_duplicate_reference_raises(self, make_user, make_wallet):
        from apps.wallet.services.wallet_service import WalletService

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("50000.00"))

        ref = f"idem_{uuid.uuid4().hex}"
        WalletService.credit(
            user=user,
            amount=Decimal("1000.00"),
            description="First credit",
            reference=ref,
        )

        from apps.wallet.services.wallet_service import DuplicateTransactionError
        with pytest.raises(DuplicateTransactionError):
            with transaction.atomic():
                WalletService.credit(
                    user=user,
                    amount=Decimal("1000.00"),
                    description="Duplicate credit",
                    reference=ref,
                )


# ── F. Concurrency ────────────────────────────────────────────────────────────


class TestWalletConcurrency:
    """10 concurrent debits of ₦1,000 must not overdraft a ₦5,000 account."""

    def test_concurrent_debits_respect_locking(self, make_user, make_wallet):
        """Only 5 debits should succeed on a ₦5,000 wallet."""
        from apps.wallet.services.wallet_service import WalletService
        from apps.wallet.models import Wallet

        user = make_user(role="vendor")
        make_wallet(user, balance=Decimal("5000.00"))

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
