import pytest
import threading
from decimal import Decimal
from django.db import transaction
from django.db.models import Sum
from apps.wallet.models import Wallet
from apps.wallet.services import WalletTransferService
from tests.factories import UserFactory

@pytest.mark.django_db(transaction=True)
class TestP2PTransferConcurrency:
    """
    Stress testing P2P transfers to ensure ACID compliance and no double-spending.
    Uses Python threading to simulate 50 concurrent transfers from a single wallet.
    """

    def test_concurrent_transfers_prevent_overdraft(self, db):
        sender = UserFactory(role='client', is_verified=True)
        receivers = [UserFactory(role='client', is_verified=True) for _ in range(10)]
        
        # Provision wallets
        from apps.wallet.services import WalletProvisioningService
        sender_wallet = WalletProvisioningService.ensure_wallet(sender)
        sender_wallet.balance = Decimal("100.00")
        sender_wallet.save()

        for r in receivers:
            WalletProvisioningService.ensure_wallet(r)

        results = []

        def perform_transfer(receiver_user):
            try:
                # Attempt to transfer $20 (Total possible: 5 successful transfers)
                WalletTransferService.transfer_p2p(
                    sender=sender,
                    receiver_identifier=receiver_user.email,
                    amount=Decimal("20.00")
                )
                results.append("success")
            except Exception as e:
                results.append(f"failed: {str(e)}")

        threads = [threading.Thread(target=perform_transfer, args=(r,)) for r in receivers]
        
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        # Verification
        sender_wallet.refresh_from_db()
        success_count = results.count("success")
        
        # We started with $100. Each transfer is $20. 
        # Max success should be exactly 5.
        assert success_count == 5
        assert sender_wallet.balance == Decimal("0.00")
        
        # Check that receivers who succeeded actually got the money
        total_received = Wallet.objects.exclude(user=sender).aggregate(total=Sum('balance'))['total']
        assert total_received == Decimal("100.00")
