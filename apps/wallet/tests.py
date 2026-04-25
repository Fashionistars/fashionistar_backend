from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from apps.transactions.models import CompanyRevenueEntry, Transaction, TransactionType
from apps.wallet.models import Wallet, WalletHoldStatus, WalletOwnerType
from apps.wallet.services import EscrowService, WalletBalanceService, WalletPinService, WalletProvisioningService


class WalletEscrowServiceTests(TestCase):
    def setUp(self):
        User = get_user_model()
        self.client_user = User.objects.create_user(email="client-wallet@example.com", password="StrongPass123!", role="client")
        self.vendor_user = User.objects.create_user(email="vendor-wallet@example.com", password="StrongPass123!", role="vendor")
        self.client_wallet = WalletProvisioningService.ensure_wallet(self.client_user)
        self.client_wallet.balance = Decimal("100000.00")
        self.client_wallet.available_balance = Decimal("100000.00")
        self.client_wallet.save(update_fields=["balance", "available_balance"])

    def test_company_wallet_receives_commission_on_escrow_release(self):
        hold = EscrowService.hold_order_payment(
            client_user=self.client_user,
            amount=Decimal("100000.00"),
            reference="ORDER-100000",
            order_id="ORDER-100000",
            idempotency_key="idem-order-100000",
        )

        result = EscrowService.release_order_payment(
            hold_reference=hold.reference,
            vendor_user=self.vendor_user,
            commission_rate=Decimal("0.10"),
            idempotency_key="idem-release-100000",
        )

        self.assertEqual(result["commission_amount"], Decimal("10000.00"))
        self.assertEqual(result["vendor_amount"], Decimal("90000.00"))
        company_wallet = Wallet.objects.get(owner_type=WalletOwnerType.COMPANY)
        vendor_wallet = Wallet.objects.get(user=self.vendor_user)
        hold.refresh_from_db()
        self.assertEqual(company_wallet.available_balance, Decimal("10000.00"))
        self.assertEqual(vendor_wallet.available_balance, Decimal("90000.00"))
        self.assertEqual(hold.status, WalletHoldStatus.RELEASED)
        self.assertTrue(Transaction.objects.filter(transaction_type=TransactionType.COMMISSION).exists())
        self.assertTrue(CompanyRevenueEntry.objects.filter(amount=Decimal("10000.00")).exists())

    def test_wallet_pin_and_transfer_create_ledger_entry(self):
        receiver = get_user_model().objects.create_user(email="receiver-wallet@example.com", password="StrongPass123!", role="client")
        WalletPinService.set_pin(self.client_user, "1234")

        result = WalletBalanceService.transfer(
            sender_user=self.client_user,
            receiver_user=receiver,
            amount=Decimal("5000.00"),
            pin="1234",
            reference="TRANSFER-5000",
            idempotency_key="idem-transfer-5000",
        )

        self.assertIn("transaction_id", result)
        self.assertTrue(Transaction.objects.filter(reference="TRANSFER-5000", transaction_type=TransactionType.TRANSFER).exists())
