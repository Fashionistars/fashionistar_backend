# apps/transactions/admin_backend/services.py
import logging

logger = logging.getLogger(__name__)

# Financial transaction records are strictly append-only.
# Manual updates are prohibited to ensure ledger integrity.
