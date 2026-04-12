# apps/authentication/selectors/session_selector.py
"""
Session & Login Event Selectors — Read-only QuerySet logic.

Architecture rule: No direct ORM calls in views. All read operations
go through selectors. All write operations go through services.

Uses:
  - select_related() for FK relationships (user, session)
  - Proper ordering for security audit display
  - Limit guards to prevent unbounded queries (default 20 sessions, 10 events)

Usage:
    from apps.authentication.selectors import get_active_sessions, get_login_events

    sessions = get_active_sessions(user=request.user, limit=20)
    events   = get_login_events(user=request.user, limit=10)
"""

from __future__ import annotations

import logging
from typing import Optional

from django.db.models import QuerySet

logger = logging.getLogger(__name__)


# ══════════════════════════════════════════════════════════════════════
# USER SESSION SELECTORS
# ══════════════════════════════════════════════════════════════════════


def get_active_sessions(
    *,
    user,
    limit: int = 20,
) -> QuerySet:
    """
    Return the most recent active sessions for a given user.

    Optimizations:
      - select_related('user') preloads user FK to avoid N+1 queries
      - Ordered by ``last_used_at`` descending (most recent first)
      - Hard-limited to ``limit`` rows (prevents unbounded table scans)

    Args:
        user:  UnifiedUser instance (the session owner).
        limit: Maximum number of sessions to return. Default: 20.

    Returns:
        QuerySet of UserSession instances, ordered by -last_used_at.
    """
    from apps.authentication.models import UserSession

    return (
        UserSession.objects
        .filter(user=user)
        .select_related('user')
        .order_by('-last_used_at')[:limit]
    )


def get_session_by_id(
    *,
    session_id: str,
    user,
) -> Optional["UserSession"]:
    """
    Fetch a specific session by PK, scoped to the given user (security).

    Args:
        session_id: UUID7 string of the session.
        user:       UnifiedUser instance (must own the session).

    Returns:
        UserSession or None if not found / belongs to different user.
    """
    from apps.authentication.models import UserSession

    try:
        return (
            UserSession.objects
            .select_related('user')
            .get(pk=session_id, user=user)
        )
    except (UserSession.DoesNotExist, ValueError, TypeError):
        return None


def get_other_sessions(
    *,
    user,
    exclude_jti: str,
) -> QuerySet:
    """
    Return all sessions for a user EXCEPT the one with ``exclude_jti``.

    Used by the "revoke all other devices" endpoint.

    Args:
        user:        UnifiedUser instance.
        exclude_jti: JTI of the session to keep (current request's session).

    Returns:
        QuerySet of UserSession instances to be revoked.
    """
    from apps.authentication.models import UserSession

    qs = UserSession.objects.filter(user=user)
    if exclude_jti:
        qs = qs.exclude(jti=exclude_jti)
    return qs


# ══════════════════════════════════════════════════════════════════════
# LOGIN EVENT SELECTORS
# ══════════════════════════════════════════════════════════════════════


def get_login_events(
    *,
    user,
    limit: int = 10,
) -> QuerySet:
    """
    Return the most recent login events (attempts) for a given user.

    Optimizations:
      - select_related('user', 'session') preloads both FKs
      - Ordered by ``created_at`` descending (most recent first)
      - Hard-limited to ``limit`` rows

    This includes BOTH successful and failed login attempts — the full
    security audit trail as shown in Binance / Google Account Security.

    Args:
        user:  UnifiedUser instance.
        limit: Maximum number of events to return. Default: 10.

    Returns:
        QuerySet of LoginEvent instances, ordered by -created_at.
    """
    from apps.authentication.models import LoginEvent

    return (
        LoginEvent.objects
        .filter(user=user)
        .select_related('user', 'session')
        .order_by('-created_at')[:limit]
    )


def get_recent_failed_logins(
    *,
    user,
    limit: int = 5,
) -> QuerySet:
    """
    Return only failed login events for a user.

    Used for security risk assessment (repeated failures = compromised account).

    Args:
        user:  UnifiedUser instance.
        limit: Maximum number of events to return. Default: 5.

    Returns:
        QuerySet of LoginEvent instances with is_successful=False.
    """
    from apps.authentication.models import LoginEvent

    return (
        LoginEvent.objects
        .filter(user=user, is_successful=False)
        .select_related('user')
        .order_by('-created_at')[:limit]
    )


def get_login_events_for_ip(
    *,
    ip_address: str,
    limit: int = 50,
) -> QuerySet:
    """
    Return login events from a specific IP address (cross-user).

    Used for threat detection: many failed logins from same IP = brute force.

    Args:
        ip_address: IP address string (IPv4 or IPv6).
        limit:      Maximum number of events. Default: 50.

    Returns:
        QuerySet of LoginEvent instances for the given IP.
    """
    from apps.authentication.models import LoginEvent

    return (
        LoginEvent.objects
        .filter(ip_address=ip_address)
        .select_related('user')
        .order_by('-created_at')[:limit]
    )
