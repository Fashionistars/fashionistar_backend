# apps/chat/admin_backend/api.py
import logging
from ninja import Router

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Chat"])

# Thin Ninja Async Read Views
