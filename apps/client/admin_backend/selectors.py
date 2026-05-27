# apps/client/admin_backend/selectors.py
import logging
from typing import Optional
from django.db import models
from django.db.models import QuerySet
from apps.client.models.client_profile import ClientProfile
from apps.client.models.client_address import ClientAddress

logger = logging.getLogger(__name__)

class AdminClientSelector:
    @classmethod
    def get_clients_list(cls, filters: dict = None) -> QuerySet:
        """
        Get all client profiles, optimized for admin changelist.
        Uses select_related to pull in user.
        """
        queryset = ClientProfile.objects.select_related("user").order_by("-created_at")
        
        if filters:
            preferred_size = filters.get("preferred_size")
            if preferred_size:
                queryset = queryset.filter(preferred_size=preferred_size)
                
            is_profile_complete = filters.get("is_profile_complete")
            if is_profile_complete is not None:
                queryset = queryset.filter(is_profile_complete=is_profile_complete)
                
            search = filters.get("search")
            if search:
                queryset = queryset.filter(
                    models.Q(user__email__icontains=search) |
                    models.Q(user__first_name__icontains=search) |
                    models.Q(user__last_name__icontains=search) |
                    models.Q(state__icontains=search) |
                    models.Q(country__icontains=search)
                )
                
        return queryset

    @classmethod
    def get_client_detail(cls, client_id: str) -> ClientProfile:
        """
        Get detail profile of a single client by profile ID or user ID.
        """
        try:
            return ClientProfile.objects.select_related("user").prefetch_related("client_addresses").get(pk=client_id)
        except (ClientProfile.DoesNotExist, ValueError):
            return ClientProfile.objects.select_related("user").prefetch_related("client_addresses").get(user_id=client_id)

    @classmethod
    def get_admin_dashboard_metrics(cls) -> dict:
        """
        Get high-level summary counts for clients.
        """
        total = ClientProfile.objects.count()
        complete = ClientProfile.objects.filter(is_profile_complete=True).count()
        incomplete = ClientProfile.objects.filter(is_profile_complete=False).count()
        
        # Calculate total spending by all clients
        total_spending = ClientProfile.objects.aggregate(total_spent=models.Sum("total_spent_ngn"))["total_spent"] or 0
        
        return {
            "total_clients": total,
            "completed_profiles": complete,
            "incomplete_profiles": incomplete,
            "total_spending_ngn": float(total_spending),
        }

    # --- Async Support ---
    
    @classmethod
    async def aget_clients_list(cls, filters: dict = None) -> list[ClientProfile]:
        """Async version of get_clients_list."""
        queryset = cls.get_clients_list(filters)
        return [client async for client in queryset]

    @classmethod
    async def aget_client_detail(cls, client_id: str) -> ClientProfile:
        """Async version of get_client_detail."""
        try:
            return await ClientProfile.objects.select_related("user").prefetch_related("client_addresses").aget(pk=client_id)
        except (ClientProfile.DoesNotExist, ValueError):
            return await ClientProfile.objects.select_related("user").prefetch_related("client_addresses").aget(user_id=client_id)

    @classmethod
    async def aget_admin_dashboard_metrics(cls) -> dict:
        """Async version of get_admin_dashboard_metrics."""
        total = await ClientProfile.objects.acount()
        complete = await ClientProfile.objects.filter(is_profile_complete=True).acount()
        incomplete = await ClientProfile.objects.filter(is_profile_complete=False).acount()
        
        # Aggregate spending
        agg = await ClientProfile.objects.aaggregate(total_spent=models.Sum("total_spent_ngn"))
        total_spending = agg["total_spent"] or 0
        
        return {
            "total_clients": total,
            "completed_profiles": complete,
            "incomplete_profiles": incomplete,
            "total_spending_ngn": float(total_spending),
        }
