# apps/product/admin_backend/services.py
import logging
from django.db import transaction
from apps.product.models import Product
from apps.product.services.product_service import approve_product, reject_product, adjust_inventory

logger = logging.getLogger(__name__)

@transaction.atomic
def admin_approve_product_sync(product_id: str, actor, request=None) -> Product:
    """
    Guarded transaction-atomic service to approve a garment.
    """
    product = Product.objects.select_for_update().get(id=product_id)
    return approve_product(product=product, actor=actor, request=request)

@transaction.atomic
def admin_reject_product_sync(product_id: str, actor, reason: str, request=None) -> Product:
    """
    Guarded transaction-atomic service to reject a garment.
    """
    product = Product.objects.select_for_update().get(id=product_id)
    return reject_product(product=product, actor=actor, reason=reason, request=request)

@transaction.atomic
def admin_adjust_inventory_sync(product_id: str, delta: int, actor, reason: str, note: str, request=None):
    """
    Guarded transaction-atomic service to adjust stock level with logs.
    """
    product = Product.objects.select_for_update().get(id=product_id)
    return adjust_inventory(
        product=product,
        quantity_delta=delta,
        reason=reason,
        actor=actor,
        note=note,
        request=request
    )
