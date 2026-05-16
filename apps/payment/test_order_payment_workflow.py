from decimal import Decimal
from unittest.mock import patch

import pytest
from django.core.cache import cache
from django.utils import timezone

from apps.order.models import (
    CashPaymentMode,
    Order,
    OrderCommercialTransitionType,
    OrderPaymentPath,
    OrderPaymentRecord,
    OrderPaymentSource,
    OrderStatus,
)
from apps.payment.cash_service import CashOrderService
from apps.payment.models import (
    PaymentIntent,
    PaymentIntentStatus,
    PaymentProviderCode,
    PaymentPurpose,
)
from apps.payment.services import PaymentIntentService
from apps.wallet.services import WalletProvisioningService


@pytest.fixture
def client_user(db, django_user_model):
    return django_user_model.objects.create_user(
        email="workflow-client@fashionistar.test",
        password="StrongPass123!",
        role="client",
        is_active=True,
        is_verified=True,
    )


@pytest.fixture
def vendor_user(db, django_user_model):
    return django_user_model.objects.create_user(
        email="workflow-vendor@fashionistar.test",
        password="StrongPass123!",
        role="vendor",
        is_active=True,
        is_verified=True,
    )


@pytest.fixture
def vendor_profile(db, vendor_user):
    from apps.vendor.models import VendorProfile

    return VendorProfile.objects.create(
        user=vendor_user,
        store_name="Workflow Test Shop",
        cash_payment_mode=CashPaymentMode.BOTH,
        is_verified=True,
    )


@pytest.fixture
def order(db, client_user, vendor_profile):
    return Order.objects.create(
        user=client_user,
        vendor=vendor_profile,
        status=OrderStatus.PENDING_PAYMENT,
        subtotal=Decimal("1000.00"),
        shipping_amount=Decimal("0.00"),
        discount_amount=Decimal("0.00"),
        total_amount=Decimal("1000.00"),
        commission_amount=Decimal("100.00"),
        vendor_payout=Decimal("900.00"),
        amount_outstanding=Decimal("1000.00"),
        currency="NGN",
        delivery_address={"address_line_1": "12 Broad Street", "city": "Lagos"},
        idempotency_key="workflow-order-idem",
        cash_payment_mode_snapshot=CashPaymentMode.BOTH,
    )


@pytest.mark.django_db
def test_wallet_payment_records_tranche_and_updates_order_aggregates(client_user, order):
    with patch("apps.payment.services.EscrowService.hold_order_payment") as mock_hold:
        intent, record = PaymentIntentService.pay_order_from_wallet(
            user=client_user,
            order=order,
            selected_percent=50,
            payment_path=OrderPaymentPath.WALLET,
            idempotency_key="wallet-order-50",
            metadata={"selected_percent": 50},
        )

    order.refresh_from_db()
    record.refresh_from_db()
    assert intent.status == PaymentIntentStatus.SUCCEEDED
    assert mock_hold.call_count == 1
    assert order.amount_paid_total == Decimal("500.00")
    assert order.percent_paid_total == Decimal("50.00")
    assert order.amount_outstanding == Decimal("500.00")
    assert order.payment_records.count() == 1
    assert record.payment_source == OrderPaymentSource.WALLET
    assert record.selected_percent == 50
    assert record.remaining_amount == Decimal("500.00")


@pytest.mark.django_db
def test_gateway_mark_success_creates_single_tranche_and_updates_order(client_user, order):
    intent = PaymentIntent.objects.create(
        user=client_user,
        provider=PaymentProviderCode.PAYSTACK,
        purpose=PaymentPurpose.ORDER_PAYMENT,
        amount=Decimal("700.00"),
        currency="NGN",
        status=PaymentIntentStatus.INITIALIZED,
        reference="FSORD_GATEWAY_70",
        provider_reference="FSORD_GATEWAY_70",
        order_id=str(order.pk),
        idempotency_key="gateway-order-70",
        metadata={"selected_percent": 70, "payment_path": OrderPaymentPath.GATEWAY},
    )

    with patch("apps.wallet.services.WalletBalanceService.credit") as mock_credit, patch(
        "apps.payment.services.EscrowService.hold_order_payment"
    ) as mock_hold:
        PaymentIntentService.mark_success(intent, {"event": "charge.success"})

    order.refresh_from_db()
    intent.refresh_from_db()
    assert intent.status == PaymentIntentStatus.SUCCEEDED
    assert mock_credit.call_count == 1
    assert mock_hold.call_count == 1
    assert order.amount_paid_total == Decimal("700.00")
    assert order.percent_paid_total == Decimal("70.00")
    assert order.amount_outstanding == Decimal("300.00")
    assert order.payment_records.count() == 1
    assert order.payment_records.first().payment_source == OrderPaymentSource.GATEWAY


@pytest.mark.django_db
def test_cash_confirmation_creates_final_offline_tranche_and_completes_order(
    client_user,
    vendor_user,
    order,
):
    order.status = OrderStatus.AWAITING_CASH_CONFIRMATION
    order.active_payment_path = OrderPaymentPath.COD
    order.amount_paid_total = Decimal("500.00")
    order.percent_paid_total = Decimal("50.00")
    order.amount_outstanding = Decimal("500.00")
    order.first_paid_at = timezone.now()
    order.delivery_mode = "cod"
    order.save(
        update_fields=[
            "status",
            "active_payment_path",
            "amount_paid_total",
            "percent_paid_total",
            "amount_outstanding",
            "first_paid_at",
            "delivery_mode",
            "updated_at",
        ]
    )
    OrderPaymentRecord.objects.create(
        order=order,
        sequence_number=1,
        payment_intent=None,
        payment_source=OrderPaymentSource.COD_COMMITMENT,
        provider=PaymentProviderCode.PAYSTACK,
        selected_percent=50,
        applied_percent=Decimal("50.00"),
        amount=Decimal("500.00"),
        currency="NGN",
        cumulative_amount_paid=Decimal("500.00"),
        cumulative_percent_paid=Decimal("50.00"),
        remaining_amount=Decimal("500.00"),
        remaining_percent=Decimal("50.00"),
        is_final_payment=False,
        paid_at=timezone.now(),
        actor=client_user,
        correlation_id="commitment-50",
        metadata={"offline": False},
    )
    intent = PaymentIntent.objects.create(
        user=client_user,
        provider=PaymentProviderCode.COD,
        purpose=PaymentPurpose.ORDER_PAYMENT,
        amount=Decimal("500.00"),
        currency="NGN",
        status=PaymentIntentStatus.PENDING,
        reference="COD_CONFIRM_REF",
        order_id=str(order.pk),
        metadata={"is_cod": True, "is_in_store": False, "requires_cash_confirmation": True},
    )

    token = "123456"
    cache.set(f"fashionistar:cod_token:{order.pk}", token, 3600)
    vendor_wallet = WalletProvisioningService.ensure_wallet(vendor_user, "NGN")
    vendor_wallet.balance = Decimal("1000.00")
    vendor_wallet.available_balance = Decimal("1000.00")
    vendor_wallet.save(update_fields=["balance", "available_balance", "updated_at"])
    WalletProvisioningService.ensure_company_wallet("NGN")

    with patch("apps.payment.cash_service.TransactionLedgerService.create_entry") as mock_entry, patch(
        "apps.payment.cash_service.CompanyRevenueEntry.objects.create"
    ) as mock_revenue_create:
        mock_entry.return_value = type("Txn", (), {"pk": "txn-1", "reference": "txn-ref"})()
        payload = CashOrderService.confirm_cod_delivery(
            order_id=str(order.pk),
            vendor_user=vendor_user,
            client_token=token,
        )
    assert mock_revenue_create.call_count == 1

    order.refresh_from_db()
    intent.refresh_from_db()
    assert payload["success"] is True
    assert intent.status == PaymentIntentStatus.SUCCEEDED
    assert order.status == OrderStatus.COMPLETED
    assert order.amount_outstanding == Decimal("0.00")
    assert order.is_fully_paid is True
    assert order.payment_records.count() == 2
    final_record = order.payment_records.order_by("-sequence_number").first()
    assert final_record.amount == Decimal("500.00")
    assert final_record.payment_source == OrderPaymentSource.MANUAL_ADJUSTMENT
    assert order.commercial_transition_logs.filter(
        transition_type=OrderCommercialTransitionType.COD_CONFIRMED
    ).exists()
