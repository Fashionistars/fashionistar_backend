# apps/transactions/admin_backend/services.py
import logging
from django.db import transaction
from apps.transactions.models import Transaction

logger = logging.getLogger(__name__)

# Financial transaction records are strictly append-only.
# Manual updates are prohibited to ensure ledger integrity.
