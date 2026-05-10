"""
Concurrency stress test: P2P wallet transfers — ACID compliance.

Verifies that simultaneous transfers from a single wallet cannot overdraft
beyond available balance (pessimistic row-locking via SELECT FOR UPDATE).

The service method is WalletBalanceService.transfer() — use the correct import.
"""
import pytest
import threading
from decimal import Decimal
from django.db.models import Sum

from apps.wallet.models import Wallet
from apps.wallet.services import WalletBalanceService, WalletProvisioningService
from tests.factories import UnifiedUserFactory


@pytest.mark.django_db(transaction=True)
class TestP2PTransferConcurrency:
    """
    Stress test P2P transfers to ensure ACID compliance and no double-spending.
    Uses Python threading to simulate 10 concurrent transfers from a single wallet.
    """

    def test_concurrent_transfers_prevent_overdraft(self, db):
        sender = UnifiedUserFactory(role="client", is_active=True, is_verified=True)
        receivers = [
            UnifiedUserFactory(role="client", is_active=True, is_verified=True)
            for _ in range(10)
        ]

        # Provision wallets
        sender_wallet = WalletProvisioningService.ensure_wallet(sender)
        sender_wallet.balance = Decimal("100.00")
        sender_wallet.available_balance = Decimal("100.00")
        sender_wallet.save()

        for r in receivers:
            WalletProvisioningService.ensure_wallet(r)

        results = []

        def perform_transfer(receiver_user):
            try:
                WalletBalanceService.transfer(
                    sender_user=sender,
                    receiver_user=receiver_user,
                    amount=Decimal("20.00"),
                    pin="0000",  # Assumes test wallet has no PIN gate in test env
                )
                results.append("success")
            except Exception as exc:
                results.append(f"failed: {exc}")

        threads = [
            threading.Thread(target=perform_transfer, args=(r,)) for r in receivers
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verification
        sender_wallet.refresh_from_db()
        success_count = results.count("success")

        # Started with $100; each transfer is $20 — max 5 should succeed.
        assert success_count <= 5
        assert sender_wallet.balance >= Decimal("0.00")

        # Receivers who succeeded should hold the transferred funds.
        total_received = (
            Wallet.objects.exclude(user=sender)
            .filter(balance__gt=0)
            .aggregate(total=Sum("balance"))["total"]
            or Decimal("0.00")
        )
        assert total_received <= Decimal("100.00")
