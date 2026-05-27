# apps/audit_logs/admin_backend/api.py
import logging
from ninja import Router

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Audit_logs"])

# Thin Ninja Async Read Views
