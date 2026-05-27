# apps/payment/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from apps.payment.admin_backend.selectors import AdminPaymentSelector
from apps.payment.admin_backend.schemas import AdminPaymentSchema

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Payment"])

@router.get("/", response=List[AdminPaymentSchema], auth=admin_auth)
async def list_payments(
    request,
    status: Optional[str] = None,
    purpose: Optional[str] = None,
    search: Optional[str] = None,
):
    """
    Get all payment intents.
    """
    filters = {"status": status, "purpose": purpose, "search": search}
    return await AdminPaymentSelector.aget_payments_list(filters)

@router.get("/{payment_intent_id}/", response=AdminPaymentSchema, auth=admin_auth)
async def get_payment_detail(request, payment_intent_id: str):
    """
    Get a specific payment intent detail.
    """
    try:
        return await AdminPaymentSelector.aget_payment_detail(payment_intent_id)
    except Exception as e:
        from ninja.errors import HttpError
        raise HttpError(404, f"Payment intent not found: {str(e)}")
