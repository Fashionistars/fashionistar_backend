# apps/transactions/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from apps.transactions.admin_backend.schemas import AdminTransactionOut
from apps.transactions.admin_backend.selectors import aget_admin_transactions

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Transactions"])

@router.get("/", response=List[AdminTransactionOut], auth=admin_auth)
async def list_transactions(
    request,
    search: Optional[str] = None,
    txn_type: Optional[str] = None,
    status: Optional[str] = None
):
    """
    Optimized async query selector for listing all ledger-tracked financial transactions.
    """
    logger.info("Admin list transactions fetched. Search: %s, Type: %s, Status: %s", search, txn_type, status)
    return await aget_admin_transactions(search_query=search, txn_type=txn_type, status=status)
