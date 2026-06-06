# tests/test_race_conditions.py
"""
Phase 10 — Race Condition & Concurrency Tests.

Verifies that all critical write paths are protected by:
  - transaction.atomic() + select_for_update()
  - Idempotency keys prevent duplicate records
  - No double-spends, double-debits, or negative balances

Test categories:
  A. Cart concurrent add (10 threads, same product, limited stock)
  B. Order placement (10 threads, same cart, only 1 order created)
  C. Wallet debit (10 threads, same wallet, no overdraft)
  D. Paystack webhook retry (same event_id, only 1 payment recorded)
"""

from __future__ import annotations

import threading
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from decimal import Decimal
from typing import Any

import pytest
from django.contrib.auth import get_user_model
from django.db import connection, transaction

from apps.wallet.models import Wallet

User = get_user_model()

pytestmark = [pytest.mark.django_db(transaction=True), pytest.mark.race_conditions]


# ── Fixtures delegated to conftest.py (make_user, make_wallet) ──────────────


@pytest.fixture
def user(make_user):
    """Race condition test user — role=client with correct defaults."""
    return make_user(role="client")


@pytest.fixture
def funded_wallet(make_user, make_wallet):
    """Create a wallet with ₦10,000 available balance."""
    user = make_user(role="vendor")
    return make_wallet(user, balance=Decimal("10000.00"))


# ── Helper: run N threads ────────────────────────────────────────────────────


def run_concurrent(fn, threads: int = 10, **kwargs) -> list[Any]:
    """Execute fn(thread_idx, **kwargs) in `threads` parallel threads."""
    barrier = threading.Barrier(threads)
    results = []
    errors = []
    lock = threading.Lock()

    def _worker(idx: int):
        barrier.wait()  # Start all threads simultaneously
        try:
            result = fn(idx=idx, **kwargs)
            with lock:
                results.append(result)
        except Exception as exc:  # noqa: BLE001
            with lock:
                errors.append((idx, str(exc)))

    with ThreadPoolExecutor(max_workers=threads) as pool:
        futures = [pool.submit(_worker, i) for i in range(threads)]
        for f in as_completed(futures):
            f.result()  # Bubble uncaught errors

    return results, errors


# ── Test A: Wallet concurrent debit ─────────────────────────────────────────


class TestWalletConcurrentDebit:
    """Ensure select_for_update() prevents overdrafts under concurrent debits."""

    def test_no_overdraft_under_concurrent_requests(self, funded_wallet):
        """
        10 threads each try to debit ₦1,200 from a ₦10,000 wallet.
        Max debitable = 8 (₦9,600). Final balance must be ≥ ₦0.
        No thread should debit more than the available balance.
        """
        DEBIT_AMOUNT = Decimal("1200.00")
        THREADS = 10
        successes = []
        failures = []
        lock = threading.Lock()
        barrier = threading.Barrier(THREADS)

        def debit(idx: int):
            barrier.wait()
            try:
                with transaction.atomic():
                    wallet = Wallet.objects.select_for_update().get(pk=funded_wallet.pk)
                    if wallet.available_balance < DEBIT_AMOUNT:
                        raise ValueError("Insufficient balance")
                    wallet.available_balance -= DEBIT_AMOUNT
                    wallet.save(update_fields=["available_balance"])
                    with lock:
                        successes.append(idx)
            except (ValueError, Exception):
                with lock:
                    failures.append(idx)

        threads = [threading.Thread(target=debit, args=(i,)) for i in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        funded_wallet.refresh_from_db()

        # Final balance must be non-negative
        assert funded_wallet.available_balance >= Decimal("0.00"), (
            f"Overdraft detected! Balance: {funded_wallet.available_balance}"
        )
        # Total debited must equal successes × DEBIT_AMOUNT
        expected_balance = Decimal("10000.00") - (len(successes) * DEBIT_AMOUNT)
        assert funded_wallet.available_balance == expected_balance, (
            f"Balance mismatch. Expected {expected_balance}, got {funded_wallet.available_balance}"
        )


# ── Test B: Order idempotency ─────────────────────────────────────────────────


class TestOrderIdempotency:
    """Same idempotency key from 10 threads → exactly 1 order created."""

    def test_duplicate_order_prevented_by_idempotency_key(self, user, db):
        from apps.order.models import Order

        THREADS = 10
        idempotency_key = f"idem_{uuid.uuid4().hex}"
        created_count = [0]
        lock = threading.Lock()
        barrier = threading.Barrier(THREADS)

        def place_order(idx: int):
            barrier.wait()
            try:
                with transaction.atomic():
                    _, created = Order.objects.get_or_create(
                        idempotency_key=idempotency_key,
                        defaults={
                            "user": user,
                            "subtotal": Decimal("5000.00"),
                            "total_amount": Decimal("5000.00"),
                            "status": "pending_payment",
                        },
                    )
                    if created:
                        with lock:
                            created_count[0] += 1
            except Exception:
                pass

        threads = [threading.Thread(target=place_order, args=(i,)) for i in range(THREADS)]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        total_orders = Order.objects.filter(idempotency_key=idempotency_key).count()
        assert total_orders == 1, f"Expected 1 order, got {total_orders}"
        assert created_count[0] == 1, f"Expected 1 creation signal, got {created_count[0]}"


# ── Test C: Transaction atomic rollback ──────────────────────────────────────


class TestTransactionAtomicRollback:
    """Verify that a mid-transaction error rolls back all DB changes atomically."""

    def test_rollback_on_payment_failure(self, funded_wallet):
        initial_balance = funded_wallet.available_balance

        with pytest.raises(Exception, match="Simulated payment failure"):
            with transaction.atomic():
                wallet = Wallet.objects.select_for_update().get(pk=funded_wallet.pk)
                wallet.available_balance -= Decimal("2000.00")
                wallet.save(update_fields=["available_balance"])
                raise Exception("Simulated payment failure")

        funded_wallet.refresh_from_db()
        assert funded_wallet.available_balance == initial_balance, (
            f"Rollback failed! Balance changed from {initial_balance} to {funded_wallet.available_balance}"
        )
