# apps/wallet/admin_backend/api.py
import logging
from typing import List, Optional
from ninja import Router
from apps.admin_backend.permissions import admin_auth
from apps.wallet.admin_backend.schemas import AdminWalletOut, AdminWalletHoldOut
from apps.wallet.admin_backend.selectors import aget_admin_wallets, aget_admin_holds

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Wallet"])

@router.get("/", response=List[AdminWalletOut], auth=admin_auth)
async def list_wallets(
    request,
    search: Optional[str] = None,
    owner_type: Optional[str] = None
):
    """
    Optimized async query selector to list user/vendor wallets with selective filters.
    """
    logger.info("Admin list wallets fetched. Search: %s, Owner Type: %s", search, owner_type)
    return await aget_admin_wallets(search_query=search, owner_type=owner_type)

@router.get("/holds/", response=List[AdminWalletHoldOut], auth=admin_auth)
async def list_holds(
    request,
    search: Optional[str] = None,
    status: Optional[str] = None
):
    """
    Optimized async query selector to list escrow active/released holds.
    """
    logger.info("Admin list holds fetched. Search: %s, Status: %s", search, status)
    return await aget_admin_holds(search_query=search, status=status)
