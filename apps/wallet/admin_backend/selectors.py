# apps/wallet/admin_backend/selectors.py
import logging
from django.contrib.auth import get_user_model
from apps.wallet.models import Wallet, WalletHold

logger = logging.getLogger(__name__)
User = get_user_model()

async def aget_admin_wallets(search_query: str = None, owner_type: str = None):
    """
    Optimized async selector for admin wallet listing.
    Prevents N+1 by selecting owners upfront.
    """
    queryset = Wallet.objects.select_related("owner")
    
    if search_query:
        queryset = queryset.filter(owner__email__icontains=search_query)
        
    if owner_type:
        queryset = queryset.filter(owner_type=owner_type)
        
    return [wallet async for wallet in queryset.order_by("-updated_at")[:100]]

async def aget_admin_holds(search_query: str = None, status: str = None):
    """
    Optimized async selector for wallet escrow holds listing.
    """
    queryset = WalletHold.objects.select_related("wallet", "wallet__owner")
    
    if search_query:
        queryset = queryset.filter(order_id__icontains=search_query)
        
    if status:
        queryset = queryset.filter(status=status)
        
    return [hold async for hold in queryset.order_by("-created_at")[:100]]
