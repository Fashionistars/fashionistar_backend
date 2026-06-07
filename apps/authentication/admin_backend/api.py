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

    payload = await async_ninja_paginate(request, qs, page=page, page_size=page_size)

    def serialize_user(user):
        return {
            "id": str(user.pk),
            "email": user.email,
            "phone": str(user.phone) if user.phone else None,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "auth_provider": user.auth_provider,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_deleted": user.is_deleted,
            "member_id": user.member_id,
            "avatar": user.avatar.url if user.avatar else None,
            "city": user.city,
            "state": user.state,
            "country": user.country,
            "bio": user.bio,
            # Phase 12 fields for card-level display
            "risk_score": float(getattr(user, "risk_score", 0.0) or 0.0),
            "two_factor_enabled": getattr(user, "two_factor_enabled", False),
            "last_login": user.last_login.isoformat() if getattr(user, "last_login", None) else None,
            "login_count": getattr(user, "login_count", 0),
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
        }

    payload["results"] = [serialize_user(u) for u in payload.get("results", [])]
    return payload


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
        # ── Phase 12: Locale & Preferences ──────────────────────────────────
        "preferred_language": getattr(user, "preferred_language", "en"),
        "timezone": getattr(user, "timezone", "UTC"),
        # ── Phase 12: 2FA ────────────────────────────────────────────────────
        "two_factor_enabled": getattr(user, "two_factor_enabled", False),
        # ── Phase 12: Login Analytics ────────────────────────────────────────
        "login_count": getattr(user, "login_count", 0),
        "last_login": user.last_login.isoformat() if getattr(user, "last_login", None) else None,
        "last_login_ip": getattr(user, "last_login_ip", None),
        "last_login_device": getattr(user, "last_login_device", ""),
        # ── Phase 12: Risk & GDPR ────────────────────────────────────────────
        "risk_score": float(getattr(user, "risk_score", 0.0) or 0.0),
        "is_processing_restricted": getattr(user, "is_processing_restricted", False),
        "processing_restriction_reason": getattr(user, "processing_restriction_reason", ""),
        "objected_processing_purposes": getattr(user, "objected_processing_purposes", []) or [],
        "marketing_consent": getattr(user, "marketing_consent", False),
        "marketing_consent_at": (
            user.marketing_consent_at.isoformat()
            if getattr(user, "marketing_consent_at", None)
            else None
        ),
        "data_retention_policy": getattr(user, "data_retention_policy", "standard"),
        # ── Phase 12: Referral ───────────────────────────────────────────────
        "referral_code": getattr(user, "referral_code", None),
        "referred_by": str(user.referred_by_id) if getattr(user, "referred_by_id", None) else None,
        # ── Timestamps ───────────────────────────────────────────────────────
        "date_joined": user.date_joined.isoformat(),
        "updated_at": user.updated_at.isoformat(),
        "deleted_at": user.deleted_at.isoformat() if getattr(user, "deleted_at", None) else None,
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
        payload = await async_ninja_paginate(request, qs, page=page, page_size=page_size)

        def serialize_session(session):
            return {
                "id": str(session.pk),
                "ip_address": session.ip_address,
                "user_agent": session.user_agent,
                "device_name": session.device_name,
                "browser_family": session.browser_family,
                "os_family": session.os_family,
                "last_used_at": session.last_used_at.isoformat() if session.last_used_at else None,
                "expires_at": session.expires_at.isoformat() if session.expires_at else None,
                "revoked_at": session.revoked_at.isoformat() if session.revoked_at else None,
                "revoked_reason": session.revoked_reason,
            }

        payload["results"] = [serialize_session(s) for s in payload.get("results", [])]
        return payload
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
        payload = await async_ninja_paginate(request, qs, page=page, page_size=page_size)

        def serialize_event(event):
            return {
                "id": str(event.pk),
                "ip_address": event.ip_address,
                "user_agent": event.user_agent,
                "client_type": event.client_type,
                "browser_family": event.browser_family,
                "os_family": event.os_family,
                "device_type": event.device_type,
                "country": event.country,
                "country_code": event.country_code,
                "region": event.region,
                "city": event.city,
                "auth_method": event.auth_method,
                "outcome": event.outcome,
                "failure_reason": event.failure_reason,
                "is_successful": event.is_successful,
                "risk_score": event.risk_score,
                "created_at": event.created_at.isoformat() if event.created_at else None,
            }

        payload["results"] = [serialize_event(e) for e in payload.get("results", [])]
        return payload
    except Exception:
        return {"success": True, "count": 0, "results": []}
