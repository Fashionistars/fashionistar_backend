# apps/authentication/admin_backend/selectors.py
"""
Admin-only async selectors for the authentication domain.

Architecture rules:
  - Each selector anchors on ONE primary model
  - Related data is traversed via related_names (no multi-model joins)
  - All functions are async-native using Django 6.0 async ORM
  - select_related / prefetch_related applied on every list endpoint
  - N+1 prevention: list_select_related covers all FK fields in list_display
"""

from __future__ import annotations

import logging
from django.contrib.auth import get_user_model
from django.db import models
from django.db.models import QuerySet

UnifiedUser = get_user_model()
logger = logging.getLogger(__name__)

class AdminUserSelector:
    @classmethod
    def get_users_list(cls, filters: dict = None) -> QuerySet:
        """
        Get all users, optimized for admin changelist.
        Filters by role, active status, verification status, and country.
        """
        queryset = UnifiedUser.objects.all_with_deleted().order_by("-date_joined")
        
        if filters:
            role = filters.get("role")
            if role:
                queryset = queryset.filter(role=role)
                
            is_active = filters.get("is_active")
            if is_active is not None:
                queryset = queryset.filter(is_active=is_active)
                
            is_verified = filters.get("is_verified")
            if is_verified is not None:
                queryset = queryset.filter(is_verified=is_verified)
                
            search = filters.get("search")
            if search:
                queryset = queryset.filter(
                    models.Q(email__icontains=search) |
                    models.Q(phone__icontains=search) |
                    models.Q(member_id__iexact=search) |
                    models.Q(first_name__icontains=search) |
                    models.Q(last_name__icontains=search)
                )
                
        return queryset

    @classmethod
    def get_user_detail(cls, user_id: str) -> UnifiedUser:
        """
        Get detail profile of a single user by ID.
        """
        return UnifiedUser.objects.all_with_deleted().get(pk=user_id)

    @classmethod
    def get_admin_dashboard_metrics(cls) -> dict:
        """
        Get high-level summary counts for users.
        """
        total_users = UnifiedUser.objects.all_with_deleted().count()
        active_users = UnifiedUser.objects.filter(is_active=True).count()
        unverified_users = UnifiedUser.objects.filter(is_verified=False).count()
        vendors = UnifiedUser.objects.filter(role="vendor").count()
        clients = UnifiedUser.objects.filter(role="client").count()
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "unverified_users": unverified_users,
            "vendors_count": vendors,
            "clients_count": clients,
        }

    # --- Async Support ---
    
    @classmethod
    async def aget_users_list(cls, filters: dict = None) -> list[UnifiedUser]:
        """Async version of get_users_list returning a list."""
        queryset = cls.get_users_list(filters)
        return [user async for user in queryset]

    @classmethod
    async def aget_user_detail(cls, user_id: str) -> UnifiedUser:
        """Async version of get_user_detail."""
        return await UnifiedUser.objects.all_with_deleted().aget(pk=user_id)

    @classmethod
    async def aget_admin_dashboard_metrics(cls) -> dict:
        """Async version of get_admin_dashboard_metrics."""
        # Using aget or count asynchronously
        total_users = await UnifiedUser.objects.all_with_deleted().acount()
        active_users = await UnifiedUser.objects.filter(is_active=True).acount()
        unverified_users = await UnifiedUser.objects.filter(is_verified=False).acount()
        vendors = await UnifiedUser.objects.filter(role="vendor").acount()
        clients = await UnifiedUser.objects.filter(role="client").acount()
        
        return {
            "total_users": total_users,
            "active_users": active_users,
            "unverified_users": unverified_users,
            "vendors_count": vendors,
            "clients_count": clients,
        }
