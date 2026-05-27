# apps/wallet/admin_backend/services.py
import logging
from django.db import transaction
from apps.wallet.models import Wallet, WalletHold

logger = logging.getLogger(__name__)

# Wallet adjustments are handled strictly via append-only transactions under apps/transactions
# admin_backend/services.py to guarantee financial integrity and avoid manual ledger updates.
