# apps/payment/admin_backend/api.py
import logging
from ninja import Router

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Payment"])

# Thin Ninja Async Read Views
