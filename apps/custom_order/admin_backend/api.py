# apps/custom_order/admin_backend/api.py
import logging
from ninja import Router

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Custom_order"])

# Thin Ninja Async Read Views
