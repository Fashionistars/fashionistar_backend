# apps/notification/admin_backend/api.py
import logging
from ninja import Router

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Notification"])

# Thin Ninja Async Read Views
