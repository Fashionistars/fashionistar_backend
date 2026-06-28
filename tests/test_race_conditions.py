"""
FASHIONISTAR — Phase 10: Race Condition + Idempotency + Transaction Atomic Tests

Tests concurrent write safety for:
  1. Race conditions — 10+ threads hitting cart/wallet/order simultaneously
  2. Idempotency — duplicate requests produce exactly one result
  3. Transaction atomic — verify rollback on partial failure

Run:
    pytest tests/test_race_conditions.py tests/test_idempotency.py tests/test_transaction_atomic.py \
           -v --tb=short -x

Requirements:
    pytest-django, factory-boy, concurrent.futures
"""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal

import pytest


# ══════════════════════════════════════════════════════════════════════════════
# RACE CONDITIONS
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
class TestWalletRaceConditions:
    """
    Verify that concurrent wallet credits/debits produce the correct final balance.
    Without select_for_update() this would fail due to lost updates.
    """

    def test_concurrent_credits_are_atomic(self, transactional_db):
        """10 concurrent ₦100 credits → final balance must be exactly ₦1,000."""
        from apps.authentication.models import UnifiedUser
        from apps.wallet.services.wallet_service import WalletService

        user = UnifiedUser.objects.create_user(
            email="wallet_race@test.com",
            password="TestPass@2026!",
            role="vendor",
            is_active=True,
            is_verified=True,
        )
        WalletService.get_or_create_wallet(user)

        errors = []
        results = []

        def credit_worker(n: int):
            try:
                txn = WalletService.credit(
                    user=user,
                    amount=Decimal("100.00"),
                    transaction_type="order_payment",
                    reference_id=f"race_credit_{n}_{uuid.uuid4().hex}",
                    description=f"Thread {n}",
                )
                results.append(txn.balance_after)
            except Exception as exc:
                errors.append(str(exc))
            finally:
                from django.db import connection
                connection.close()

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(credit_worker, i) for i in range(10)]
            for f in as_completed(futures):
                f.result()

        from apps.wallet.models import Wallet
        final_wallet = Wallet.objects.get(user=user)

        assert not errors, f"Errors during concurrent credits: {errors}"
        assert final_wallet.available_balance == Decimal("1000.00"), (
            f"Race condition: expected ₦1,000 but got ₦{final_wallet.available_balance}"
        )

    def test_concurrent_debits_prevent_negative_balance(self, transactional_db):
        """10 concurrent ₦100 debits on ₦500 wallet → exactly 5 succeed, 5 raise InsufficientFunds."""
        from apps.authentication.models import UnifiedUser
        from apps.wallet.services.wallet_service import WalletService, InsufficientFundsError

        user = UnifiedUser.objects.create_user(
            email="wallet_debit_race@test.com",
            password="TestPass@2026!",
            role="vendor",
            is_active=True,
            is_verified=True,
        )
        wallet = WalletService.get_or_create_wallet(user)
        # Prime with ₦500
        WalletService.credit(
            user=user, amount=Decimal("500.00"),
            transaction_type="order_payment", reference_id="prime_500",
        )

        successes = []
        failures = []

        def debit_worker(n: int):
            try:
                WalletService.debit(
                    user=user,
                    amount=Decimal("100.00"),
                    transaction_type="payout",
                    reference_id=f"race_debit_{n}_{uuid.uuid4().hex}",
                )
                successes.append(n)
            except InsufficientFundsError:
                failures.append(n)
            finally:
                from django.db import connection
                connection.close()

        with ThreadPoolExecutor(max_workers=10) as pool:
            futures = [pool.submit(debit_worker, i) for i in range(10)]
            for f in as_completed(futures):
                f.result()

        wallet.refresh_from_db()
        assert wallet.available_balance >= Decimal("0"), "Wallet went negative — race condition detected!"
        assert len(successes) == 5, f"Expected 5 successful debits, got {len(successes)}"
        assert len(failures) == 5, f"Expected 5 InsufficientFunds, got {len(failures)}"


# ══════════════════════════════════════════════════════════════════════════════
# IDEMPOTENCY
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
class TestWalletIdempotency:
    """WalletTransaction.reference_id uniqueness guarantees idempotency."""

    def test_duplicate_credit_raises_error(self, transactional_db):
        from apps.authentication.models import UnifiedUser
        from apps.wallet.services.wallet_service import WalletService, DuplicateTransactionError

        user = UnifiedUser.objects.create_user(
            email="idempotent_credit@test.com",
            password="TestPass@2026!",
            role="vendor",
            is_active=True,
            is_verified=True,
        )
        WalletService.get_or_create_wallet(user)

        ref_id = f"idem_{uuid.uuid4().hex}"
        # First call succeeds
        WalletService.credit(
            user=user, amount=Decimal("500.00"),
            transaction_type="order_payment", reference_id=ref_id,
        )

        # Second identical call must raise
        with pytest.raises(DuplicateTransactionError):
            WalletService.credit(
                user=user, amount=Decimal("500.00"),
                transaction_type="order_payment", reference_id=ref_id,
            )

    def test_concurrent_duplicate_credits_only_one_succeeds(self, transactional_db):
        """Simulate payment webhook retry: only 1 of 5 concurrent identical calls succeeds."""
        from apps.authentication.models import UnifiedUser
        from apps.wallet.services.wallet_service import WalletService, DuplicateTransactionError

        user = UnifiedUser.objects.create_user(
            email="idempotent_concurrent@test.com",
            password="TestPass@2026!",
            role="vendor",
            is_active=True,
            is_verified=True,
        )
        WalletService.get_or_create_wallet(user)

        ref_id = f"webhook_retry_{uuid.uuid4().hex}"
        successes = []
        failures = []

        def attempt(_):
            try:
                WalletService.credit(
                    user=user, amount=Decimal("1000.00"),
                    transaction_type="order_payment", reference_id=ref_id,
                )
                successes.append(1)
            except DuplicateTransactionError:
                failures.append(1)
            finally:
                from django.db import connection
                connection.close()

        with ThreadPoolExecutor(max_workers=5) as pool:
            futures = [pool.submit(attempt, i) for i in range(5)]
            for f in as_completed(futures):
                f.result()

        from apps.wallet.models import Wallet
        wallet = Wallet.objects.get(user=user)
        assert wallet.available_balance == Decimal("1000.00"), (
            f"Idempotency broken: balance={wallet.available_balance}, "
            f"successes={len(successes)}, failures={len(failures)}"
        )
        assert len(successes) == 1, f"More than 1 credit succeeded: {len(successes)}"


# ══════════════════════════════════════════════════════════════════════════════
# TRANSACTION ATOMIC ROLLBACK
# ══════════════════════════════════════════════════════════════════════════════


@pytest.mark.django_db(transaction=True)
class TestTransactionAtomicRollback:
    """Verify that failures inside transaction.atomic() roll back ALL changes."""

    def test_wallet_credit_rollback_on_audit_failure(self, transactional_db, mocker):
        """
        Simulate: wallet balance updated but audit log creation fails.
        The entire transaction must roll back — balance unchanged.
        """
        from apps.authentication.models import UnifiedUser
        from apps.wallet.models import Wallet, WalletTransaction
        from apps.wallet.services.wallet_service import WalletService

        user = UnifiedUser.objects.create_user(
            email="rollback_test@test.com",
            password="TestPass@2026!",
            role="vendor",
            is_active=True,
            is_verified=True,
        )
        WalletService.get_or_create_wallet(user)
        initial_balance = Wallet.objects.get(user=user).available_balance

        # Patch WalletTransaction.objects.create to raise after wallet balance update
        original_create = WalletTransaction.objects.create

        call_count = [0]
        def failing_create(**kwargs):
            call_count[0] += 1
            raise Exception("Simulated DB failure on WalletTransaction.create")

        mocker.patch.object(WalletTransaction.objects, "create", side_effect=failing_create)

        with pytest.raises(Exception, match="Simulated DB failure"):
            WalletService.credit(
                user=user, amount=Decimal("500.00"),
                transaction_type="order_payment",
                reference_id=f"rollback_{uuid.uuid4().hex}",
            )

        # Wallet balance MUST be unchanged — rollback verified
        wallet = Wallet.objects.get(user=user)
        assert wallet.available_balance == initial_balance, (
            f"Rollback failed: balance changed from {initial_balance} to {wallet.available_balance}"
        )

    def test_escrow_hold_rollback_on_insufficient_funds(self, transactional_db):
        """Escrow hold on insufficient balance must not partially commit."""
        from apps.authentication.models import UnifiedUser
        from apps.wallet.models import Wallet
        from apps.wallet.services.wallet_service import WalletService, InsufficientFundsError

        user = UnifiedUser.objects.create_user(
            email="escrow_rollback@test.com",
            password="TestPass@2026!",
            role="client",
            is_active=True,
            is_verified=True,
        )
        WalletService.get_or_create_wallet(user)
        # Prime ₦100
        WalletService.credit(
            user=user, amount=Decimal("100.00"),
            transaction_type="deposit", reference_id=f"prime_{uuid.uuid4().hex}",
        )

        wallet_before = Wallet.objects.get(user=user)
        avail_before = wallet_before.available_balance
        held_before = wallet_before.held_balance

        # Try to hold ₦500 (more than available)
        with pytest.raises(InsufficientFundsError):
            WalletService.escrow_hold(
                user=user, amount=Decimal("500.00"),
                order_reference=f"order_{uuid.uuid4().hex}",
            )

        wallet_after = Wallet.objects.get(user=user)
        assert wallet_after.available_balance == avail_before, "available_balance changed after failed escrow hold"
        assert wallet_after.held_balance == held_before, "held_balance changed after failed escrow hold"
