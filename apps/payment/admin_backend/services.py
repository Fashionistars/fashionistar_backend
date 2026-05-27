# apps/payment/admin_backend/services.py
from __future__ import annotations
import logging
from decimal import Decimal
from django.db import transaction
from apps.common.events import event_bus
from apps.payment.models import PaymentIntent, PaymentIntentStatus

logger = logging.getLogger(__name__)

@transaction.atomic
def admin_refund_payment_intent(
    payment_intent_id: str,
    admin_user,
    amount: Decimal,
    reason: str = "",
) -> PaymentIntent:
    """
    Simulates refunding a payment intent or records a refund.
    In a real system, this would interact with Stripe/Paystack APIs.
    """
    intent = PaymentIntent.objects.select_for_update().get(id=payment_intent_id)
    if intent.status != PaymentIntentStatus.SUCCEEDED:
        raise ValueError(f"Cannot refund payment intent in status: {intent.status}")
        
    intent.status = PaymentIntentStatus.CANCELLED
    intent.metadata["refunded_by"] = admin_user.email
    intent.metadata["refund_amount"] = str(amount)
    intent.metadata["refund_reason"] = reason
    intent.save()
    
    logger.info("Admin %s refunded payment intent %s", admin_user.email, payment_intent_id)
    event_bus.emit_on_commit(
        "admin.payment.intent_refunded",
        payment_intent_id=str(intent.id),
        amount=str(amount),
        admin_id=str(admin_user.id),
    )
    return intent
