# apps/authentication/admin_backend/api.py
"""
Django Ninja async read API for the authentication admin domain.

Aligned to the class-based AdminUserSelector and Ninja Schema patterns
established in selectors.py and schemas.py.

GET  /api/admin/auth/users/               → paginated users list
GET  /api/admin/auth/users/stats/         → KPI metrics
GET  /api/admin/auth/users/{id}/          → user detail
"""

from __future__ import annotations

import logging
from typing import Optional, List

from ninja import Router

from apps.admin_backend.permissions import admin_auth
from .selectors import AdminUserSelector
from .schemas import (
    UnifiedUserListSchema,
    UnifiedUserDetailSchema,
    UserMetricsSchema,
)

logger = logging.getLogger(__name__)

router = Router(tags=["Admin - Authentication"])


# ─────────────────────────────────────────────────────────────────────────────
# Users — List
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/users/",
    summary="Admin: List All Users",
    auth=admin_auth,
)
async def admin_list_users(
    request,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    is_verified: Optional[bool] = None,
    search: Optional[str] = None,
    ordering: str = "-date_joined",
    page: int = 1,
    page_size: int = 25,
):
    """
    Paginated list of all users (including soft-deleted).
    Delegates to AdminUserSelector.get_users_list() with async pagination.
    """
    from apps.common.pagination import async_ninja_paginate

    filters = {
        k: v for k, v in {
            "role": role,
            "is_active": is_active,
            "is_verified": is_verified,
            "search": search,
        }.items() if v is not None
    }

    qs = AdminUserSelector.get_users_list(filters=filters or None)

    # Apply ordering
    qs = qs.order_by(ordering)

    return await async_ninja_paginate(request, qs, page=page, page_size=page_size)


# ─────────────────────────────────────────────────────────────────────────────
# Users — KPI Stats
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/users/stats/",
    response=UserMetricsSchema,
    summary="Admin: User KPI Metrics",
    auth=admin_auth,
)
async def admin_user_stats(request):
    """Async aggregate user stats for the admin dashboard KPI cards."""
    return await AdminUserSelector.aget_admin_dashboard_metrics()


# ─────────────────────────────────────────────────────────────────────────────
# Users — Detail
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/users/{user_id}/",
    summary="Admin: User Detail",
    auth=admin_auth,
)
async def admin_user_detail(request, user_id: str):
    """Full user detail including profile fields."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    try:
        user = await AdminUserSelector.aget_user_detail(user_id)
    except User.DoesNotExist:
        return {"success": False, "message": "User not found."}

    return {
        "id": str(user.pk),
        "email": user.email,
        "phone": str(user.phone) if user.phone else None,
        "first_name": user.first_name,
        "last_name": user.last_name,
        "member_id": user.member_id,
        "role": user.role,
        "auth_provider": user.auth_provider,
        "is_active": user.is_active,
        "is_verified": user.is_verified,
        "is_deleted": user.is_deleted,
        "is_superuser": user.is_superuser,
        "is_staff": user.is_staff,
        "bio": user.bio,
        "country": user.country,
        "state": user.state,
        "city": user.city,
        "address": user.address,
        "avatar": user.avatar.url if user.avatar else None,
        "date_joined": user.date_joined.isoformat(),
        "updated_at": user.updated_at.isoformat(),
        "deleted_at": getattr(user, "deleted_at", None) and user.deleted_at.isoformat(),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sessions — per user
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/users/{user_id}/sessions/",
    summary="Admin: User Active Sessions",
    auth=admin_auth,
)
async def admin_user_sessions(request, user_id: str, page: int = 1, page_size: int = 25):
    """List active sessions for a specific user (security audit tab)."""
    from apps.common.pagination import async_ninja_paginate

    try:
        from apps.authentication.models import UserSession
        qs = (
            UserSession.objects.filter(user_id=user_id)
            .select_related("user")
            .order_by("-created_at")
        )
        return await async_ninja_paginate(request, qs, page=page, page_size=page_size)
    except Exception:
        # UserSession model may not exist in all environments
        return {"success": True, "count": 0, "results": []}


# ─────────────────────────────────────────────────────────────────────────────
# Login Events — per user
# ─────────────────────────────────────────────────────────────────────────────

@router.get(
    "/users/{user_id}/events/",
    summary="Admin: User Login Events",
    auth=admin_auth,
)
async def admin_user_login_events(request, user_id: str, page: int = 1, page_size: int = 25):
    """List login events for a specific user."""
    from apps.common.pagination import async_ninja_paginate

    try:
        from apps.authentication.models import LoginEvent
        qs = (
            LoginEvent.objects.filter(user_id=user_id)
            .select_related("user")
            .order_by("-created_at")
        )
        return await async_ninja_paginate(request, qs, page=page, page_size=page_size)
    except Exception:
        return {"success": True, "count": 0, "results": []}
