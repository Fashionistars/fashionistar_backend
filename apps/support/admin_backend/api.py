# apps/support/admin_backend/api.py
import logging
from ninja import Router

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Support"])

# Thin Ninja Async Read Views
