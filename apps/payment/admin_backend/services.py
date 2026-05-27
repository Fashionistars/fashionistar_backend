# apps/payment/admin_backend/services.py
import logging
from django.db import transaction
from apps.common.services import emit_on_commit

logger = logging.getLogger(__name__)

# Basic Admin Write Services with Transaction Atomic & Event Bus
