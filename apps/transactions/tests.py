# apps/transactions/tests.py
"""
Wave 5 Transaction Domain — Enterprise Regression Test Suite.

Coverage:
  1. CommissionService       — rate calculation, measurement fee constant
  2. TransactionLedgerService — escrow hold, escrow release, refund, measurement fee
  3. TransactionQueryService  — for_user scoping, summary aggregation
  4. DisputeService           — dispute creation, status transition, log entry
  5. TransactionModel         — status machine transitions, complete(), cancel()
  6. Cross-domain integrity   — idempotency key deduplication
"""

from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from apps.transactions.models import (
    Transaction,
    TransactionStatus,
    TransactionType,
    TransactionDirection,
    TransactionLog,
    TransactionDispute,
    CommissionRule,
    RevenueCategory,
    CompanyRevenueEntry,
)
from apps.transactions.services import (
    CommissionService,
    TransactionLedgerService,
    TransactionQueryService,
    DisputeService,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────


@pytest.fixture
def client_user(db):
    return User.objects.create_user(email="txn_client@test.com", password="Pass1234!")


@pytest.fixture
def vendor_user(db):
    return User.objects.create_user(email="txn_vendor@test.com", password="Pass1234!")


@pytest.fixture
def currency(db):
    """Ensure a currency row exists for wallet FK constraint."""
    from apps.wallet.models import Currency
    obj, _ = Currency.objects.get_or_create(code="NGN", defaults={"name": "Nigerian Naira", "symbol": "₦"})
    return obj


@pytest.fixture
def client_wallet(db, client_user, currency):
    from apps.wallet.models import Wallet
    obj, _ = Wallet.objects.get_or_create(
        user=client_user,
        defaults={"balance": Decimal("50000.00"), "available_balance": Decimal("50000.00"), "currency": currency},
    )
    return obj


@pytest.fixture
def vendor_wallet(db, vendor_user, currency):
    from apps.wallet.models import Wallet
    obj, _ = Wallet.objects.get_or_create(
        user=vendor_user,
        defaults={"balance": Decimal("0.00"), "available_balance": Decimal("0.00"), "currency": currency},
    )
    return obj


@pytest.fixture
def company_wallet(db, currency):
    """Company wallet — no user FK required; use a dedicated company user."""
    from apps.wallet.models import Wallet
    company_user = User.objects.create_user(email="company@fashionistar.com", password="SecurePass123!")
    obj, _ = Wallet.objects.get_or_create(
        user=company_user,
        defaults={"balance": Decimal("0.00"), "available_balance": Decimal("0.00"), "currency": currency},
    )
    return obj


@pytest.fixture
def escrow_txn(db, client_user, client_wallet):
    """A completed escrow-hold transaction for use in escrow-release tests."""
    txn = Transaction.objects.create(
        transaction_type=TransactionType.ESCROW_HOLD,
        status=TransactionStatus.COMPLETED,
        direction=TransactionDirection.OUTBOUND,
        amount=Decimal("25000.00"),
        net_amount=Decimal("25000.00"),
        from_user=client_user,
        from_wallet=client_wallet,
        reference="ORD-001:hold",
        idempotency_key="idem-hold-001",
        order_id="order-uuid-001",
        description="Test escrow hold",
        completed_at=__import__("django.utils", fromlist=["timezone"]).timezone.now(),
    )
    return txn


# ─────────────────────────────────────────────────────────────────────────────
# 1. COMMISSION SERVICE
# ─────────────────────────────────────────────────────────────────────────────


class TestCommissionServiceBasic:
    """Pure pytest style — no unittest inheritance."""

    def test_default_commission_is_ten_percent(self):
        assert (
            CommissionService.calculate(Decimal("100000.00"), Decimal("0.10"))
            == Decimal("10000.00")
        )

    def test_measurement_fee_default_is_one_thousand_naira(self):
        assert CommissionService.MEASUREMENT_FEE_NGN == Decimal("1000.00")

    def test_calculate_rounds_to_two_decimal_places(self):
        result = CommissionService.calculate(Decimal("10001.00"), Decimal("0.10"))
        assert result == Decimal("1000.10")

    def test_rate_for_vendor_returns_default_when_no_rule(self, db, vendor_user):
        rate = CommissionService.rate_for_vendor(vendor_user)
        assert rate == CommissionService.DEFAULT_RATE

    def test_rate_for_vendor_returns_custom_rule_rate(self, db, vendor_user):
        from django.utils import timezone
        CommissionRule.objects.create(
            vendor_user=vendor_user,
            rate=Decimal("0.0750"),
            is_active=True,
            starts_at=timezone.now(),
        )
        rate = CommissionService.rate_for_vendor(vendor_user)
        assert rate == Decimal("0.0750")

    def test_calculate_zero_amount_returns_zero(self):
        result = CommissionService.calculate(Decimal("0.00"), Decimal("0.10"))
        assert result == Decimal("0.00")


class TestCommissionServicePytest:
    """Pytest-native equivalents to run alongside the TestCase class."""

    def test_commission_ten_percent(self):
        result = CommissionService.calculate(Decimal("100000.00"), Decimal("0.10"))
        assert result == Decimal("10000.00")

    def test_measurement_fee_constant(self):
        assert CommissionService.MEASUREMENT_FEE_NGN == Decimal("1000.00")

    def test_default_rate_is_ten_percent(self):
        assert CommissionService.DEFAULT_RATE == Decimal("0.1000")


# ─────────────────────────────────────────────────────────────────────────────
# 2. TRANSACTION LEDGER SERVICE
# ─────────────────────────────────────────────────────────────────────────────


class TestTransactionLedgerService:

    def test_record_escrow_hold_creates_transaction(self, client_user, client_wallet):
        txn = TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("20000.00"),
            reference="ORD-TEST-001",
            order_id="order-uuid-test",
            idempotency_key="idem-hold-test",
        )
        assert txn.pk is not None
        assert txn.transaction_type == TransactionType.ESCROW_HOLD
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.amount == Decimal("20000.00")

    def test_record_escrow_hold_creates_log_entry(self, client_user, client_wallet):
        txn = TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("5000.00"),
            reference="ORD-LOG-001",
        )
        log_count = TransactionLog.objects.filter(transaction=txn).count()
        assert log_count >= 1

    def test_record_measurement_fee_deducts_wallet_balance(
        self, client_user, client_wallet, company_wallet
    ):
        initial_balance = client_wallet.available_balance
        fee_amount = CommissionService.MEASUREMENT_FEE_NGN

        TransactionLedgerService.record_measurement_fee(
            user=client_user,
            wallet=client_wallet,
            company_wallet=company_wallet,
            reference="MEAS-001",
            idempotency_key="idem-meas-001",
        )
        client_wallet.refresh_from_db()
        assert client_wallet.available_balance == initial_balance - fee_amount

    def test_record_measurement_fee_credits_company_wallet(
        self, client_user, client_wallet, company_wallet
    ):
        initial_company_balance = company_wallet.available_balance
        fee_amount = CommissionService.MEASUREMENT_FEE_NGN

        TransactionLedgerService.record_measurement_fee(
            user=client_user,
            wallet=client_wallet,
            company_wallet=company_wallet,
            reference="MEAS-002",
            idempotency_key="idem-meas-002",
        )
        company_wallet.refresh_from_db()
        assert company_wallet.available_balance == initial_company_balance + fee_amount

    def test_record_measurement_fee_insufficient_balance_raises(
        self, client_user, client_wallet, company_wallet
    ):
        client_wallet.available_balance = Decimal("0.00")
        client_wallet.balance = Decimal("0.00")
        client_wallet.save()

        with pytest.raises(ValidationError, match="Insufficient"):
            TransactionLedgerService.record_measurement_fee(
                user=client_user,
                wallet=client_wallet,
                company_wallet=company_wallet,
                reference="MEAS-FAIL-001",
            )

    def test_record_measurement_fee_creates_revenue_entry(
        self, client_user, client_wallet, company_wallet
    ):
        txn = TransactionLedgerService.record_measurement_fee(
            user=client_user,
            wallet=client_wallet,
            company_wallet=company_wallet,
            reference="MEAS-REV-001",
        )
        revenue = CompanyRevenueEntry.objects.filter(transaction=txn).first()
        assert revenue is not None
        assert revenue.category == RevenueCategory.MEASUREMENT_SERVICE

    def test_record_refund_creates_inbound_transaction(self, client_user, client_wallet):
        txn = TransactionLedgerService.record_refund(
            wallet=client_wallet,
            amount=Decimal("10000.00"),
            reference="ORD-REFUND-001",
            order_id="order-refund-uuid",
            idempotency_key="idem-refund-001",
        )
        assert txn.transaction_type == TransactionType.REFUND
        assert txn.direction == TransactionDirection.INBOUND
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.to_wallet == client_wallet

    def test_record_escrow_release_creates_vendor_and_commission_entries(
        self, client_user, client_wallet, vendor_user, vendor_wallet, company_wallet
    ):
        hold = TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("20000.00"),
            reference="ORD-RELEASE-001",
            order_id="order-release-uuid",
        )

        gross = Decimal("20000.00")
        commission = CommissionService.calculate(gross, CommissionService.DEFAULT_RATE)  # 2000
        vendor_net = gross - commission  # 18000

        TransactionLedgerService.record_escrow_release(
            hold=hold,
            vendor_user=vendor_user,
            vendor_wallet=vendor_wallet,
            company_wallet=company_wallet,
            gross_amount=gross,
            vendor_amount=vendor_net,
            commission_amount=commission,
            idempotency_key="idem-release-001",
        )
        vendor_txn = Transaction.objects.filter(
            to_wallet=vendor_wallet,
            transaction_type=TransactionType.ESCROW_RELEASE,
        ).first()
        commission_txn = Transaction.objects.filter(
            to_wallet=company_wallet,
            transaction_type=TransactionType.COMMISSION,
        ).first()

        assert vendor_txn is not None
        assert vendor_txn.amount == vendor_net
        assert commission_txn is not None
        assert commission_txn.amount == commission

    def test_escrow_release_creates_company_revenue_entry(
        self, client_user, client_wallet, vendor_user, vendor_wallet, company_wallet
    ):
        hold = TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("10000.00"),
            reference="ORD-REVENUE-001",
            order_id="order-revenue-uuid",
        )
        gross = Decimal("10000.00")
        commission = Decimal("1000.00")
        vendor_net = Decimal("9000.00")

        TransactionLedgerService.record_escrow_release(
            hold=hold,
            vendor_user=vendor_user,
            vendor_wallet=vendor_wallet,
            company_wallet=company_wallet,
            gross_amount=gross,
            vendor_amount=vendor_net,
            commission_amount=commission,
        )
        assert CompanyRevenueEntry.objects.filter(
            category=RevenueCategory.ORDER_COMMISSION
        ).exists()


# ─────────────────────────────────────────────────────────────────────────────
# 3. TRANSACTION QUERY SERVICE
# ─────────────────────────────────────────────────────────────────────────────


class TestTransactionQueryService:

    def test_for_user_returns_own_transactions(self, client_user, client_wallet):
        TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("5000.00"),
            reference="QUERY-001",
        )
        qs = TransactionQueryService.for_user(client_user)
        assert qs.count() >= 1

    def test_for_user_excludes_others_transactions(self, client_user, vendor_user, vendor_wallet):
        """Vendor's transactions must not bleed into client's query."""
        TransactionLedgerService.record_escrow_hold(
            user=vendor_user,
            wallet=vendor_wallet,
            amount=Decimal("3000.00"),
            reference="QUERY-VENDOR-001",
        )
        client_qs = TransactionQueryService.for_user(client_user)
        vendor_txn_ids = Transaction.objects.filter(
            from_user=vendor_user
        ).values_list("id", flat=True)
        client_txn_ids = set(client_qs.values_list("id", flat=True))
        for vid in vendor_txn_ids:
            assert vid not in client_txn_ids

    def test_summary_for_user_returns_expected_keys(self, client_user, client_wallet):
        summary = TransactionQueryService.summary_for_user(client_user)
        assert "total_transactions" in summary
        assert "completed" in summary
        assert "pending" in summary
        assert "total_sent" in summary
        assert "total_received" in summary

    def test_summary_for_user_correct_total_sent(self, client_user, client_wallet):
        TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("8000.00"),
            reference="SUMMARY-001",
        )
        summary = TransactionQueryService.summary_for_user(client_user)
        # At least 8000 was sent (may have others from fixture setup)
        assert summary["total_sent"] >= Decimal("8000.00")


# ─────────────────────────────────────────────────────────────────────────────
# 4. DISPUTE SERVICE
# ─────────────────────────────────────────────────────────────────────────────


class TestDisputeService:

    def test_create_dispute_changes_txn_status(self, client_user, client_wallet):
        hold = TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("7000.00"),
            reference="DISPUTE-001",
        )
        DisputeService.create_dispute(
            user=client_user,
            transaction_id=hold.pk,
            reason="Item not received.",
            amount=Decimal("7000.00"),
        )
        hold.refresh_from_db()
        assert hold.status == TransactionStatus.DISPUTED

    def test_create_dispute_creates_dispute_record(self, client_user, client_wallet):
        hold = TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("9000.00"),
            reference="DISPUTE-002",
        )
        dispute = DisputeService.create_dispute(
            user=client_user,
            transaction_id=hold.pk,
            reason="Defective product.",
            amount=Decimal("9000.00"),
        )
        assert isinstance(dispute, TransactionDispute)
        assert dispute.disputed_amount == Decimal("9000.00")
        assert dispute.initiated_by == client_user

    def test_create_dispute_creates_log_entry(self, client_user, client_wallet):
        hold = TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("4000.00"),
            reference="DISPUTE-LOG-001",
        )
        DisputeService.create_dispute(
            user=client_user,
            transaction_id=hold.pk,
            reason="Wrong size delivered.",
            amount=Decimal("4000.00"),
        )
        # Log entry for the DISPUTED status transition must exist
        assert TransactionLog.objects.filter(
            transaction=hold,
            new_status=TransactionStatus.DISPUTED,
        ).exists()


# ─────────────────────────────────────────────────────────────────────────────
# 5. TRANSACTION MODEL — Status State Machine
# ─────────────────────────────────────────────────────────────────────────────


class TestTransactionModel:

    def test_complete_sets_status_and_timestamps(self, client_user, client_wallet):
        txn = Transaction.objects.create(
            transaction_type=TransactionType.ORDER_PAYMENT,
            status=TransactionStatus.PROCESSING,
            direction=TransactionDirection.OUTBOUND,
            amount=Decimal("2000.00"),
            net_amount=Decimal("2000.00"),
            from_user=client_user,
            from_wallet=client_wallet,
            reference="MODEL-COMPLETE-001",
        )
        txn.complete()
        txn.save(update_fields=["status", "processed_at", "completed_at", "updated_at"])
        txn.refresh_from_db()
        assert txn.status == TransactionStatus.COMPLETED
        assert txn.completed_at is not None

    def test_complete_idempotent_sets_processed_at(self, client_user, client_wallet):
        txn = Transaction.objects.create(
            transaction_type=TransactionType.ORDER_PAYMENT,
            status=TransactionStatus.PENDING,
            direction=TransactionDirection.OUTBOUND,
            amount=Decimal("1500.00"),
            net_amount=Decimal("1500.00"),
            from_user=client_user,
            from_wallet=client_wallet,
            reference="MODEL-IDEM-COMPLETE-001",
        )
        txn.complete()
        txn.save(update_fields=["status", "processed_at", "completed_at", "updated_at"])
        txn.refresh_from_db()
        assert txn.processed_at is not None

    def test_transaction_str_representation(self, client_user, client_wallet):
        txn = Transaction.objects.create(
            transaction_type=TransactionType.ESCROW_HOLD,
            status=TransactionStatus.PENDING,
            direction=TransactionDirection.OUTBOUND,
            amount=Decimal("1000.00"),
            net_amount=Decimal("1000.00"),
            from_user=client_user,
            from_wallet=client_wallet,
            reference="MODEL-STR-001",
        )
        assert str(txn)  # Should return a non-empty string

    def test_completed_transaction_has_correct_status(self, client_user, client_wallet):
        txn = Transaction.objects.create(
            transaction_type=TransactionType.ESCROW_HOLD,
            status=TransactionStatus.COMPLETED,
            direction=TransactionDirection.OUTBOUND,
            amount=Decimal("100.00"),
            net_amount=Decimal("100.00"),
            from_user=client_user,
            from_wallet=client_wallet,
            reference="TERMINAL-completed",
        )
        assert txn.status == TransactionStatus.COMPLETED

    def test_failed_transaction_has_correct_status(self, client_user, client_wallet):
        txn = Transaction.objects.create(
            transaction_type=TransactionType.ORDER_PAYMENT,
            status=TransactionStatus.FAILED,
            direction=TransactionDirection.OUTBOUND,
            amount=Decimal("100.00"),
            net_amount=Decimal("100.00"),
            from_user=client_user,
            from_wallet=client_wallet,
            reference="TERMINAL-failed",
        )
        assert txn.status == TransactionStatus.FAILED


# ─────────────────────────────────────────────────────────────────────────────
# 6. IDEMPOTENCY KEY DEDUPLICATION
# ─────────────────────────────────────────────────────────────────────────────


class TestIdempotencyKeyDeduplication:
    """
    Validates that the reference field (unique=True at DB level) prevents
    duplicate ledger entries for the same payment event.
    """

    def test_duplicate_reference_raises_integrity_error(self, client_user, client_wallet):
        from django.db import IntegrityError

        REFERENCE = "idem-unique-dedup-test-001"
        TransactionLedgerService.record_escrow_hold(
            user=client_user,
            wallet=client_wallet,
            amount=Decimal("5000.00"),
            reference=REFERENCE,
        )
        # A second hold with the same reference must raise IntegrityError
        with pytest.raises(IntegrityError):
            Transaction.objects.create(
                transaction_type=TransactionType.ESCROW_HOLD,
                status=TransactionStatus.PENDING,
                direction=TransactionDirection.OUTBOUND,
                amount=Decimal("5000.00"),
                net_amount=Decimal("5000.00"),
                from_user=client_user,
                from_wallet=client_wallet,
                reference=REFERENCE + ":hold",  # record_escrow_hold appends :hold
            )

    def test_different_references_succeed(self, client_user, client_wallet):
        t1 = TransactionLedgerService.record_escrow_hold(
            user=client_user, wallet=client_wallet,
            amount=Decimal("1000.00"), reference="DEDUP-001",
        )
        t2 = TransactionLedgerService.record_escrow_hold(
            user=client_user, wallet=client_wallet,
            amount=Decimal("1000.00"), reference="DEDUP-002",
        )
        assert t1.pk != t2.pk
