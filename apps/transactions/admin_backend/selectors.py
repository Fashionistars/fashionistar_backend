# apps/transactions/admin_backend/selectors.py
import logging
from apps.transactions.models import Transaction

logger = logging.getLogger(__name__)

async def aget_admin_transactions(search_query: str = None, txn_type: str = None, status: str = None):
    """
    Optimized async selector for financial transactions listing.
    Prevents N+1 by selecting user/vendor upfront.
    """
    queryset = Transaction.objects.select_related("user", "vendor")
    
    if search_query:
        from django.db.models import Q
        queryset = queryset.filter(
            Q(reference__icontains=search_query) |
            Q(user__email__icontains=search_query) |
            Q(vendor__store_name__icontains=search_query)
        )
        
    if txn_type:
        queryset = queryset.filter(type=txn_type)
        
    if status:
        queryset = queryset.filter(status=status)
        
    return [txn async for txn in queryset.order_by("-created_at")[:100]]
