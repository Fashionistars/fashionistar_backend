# apps/authentication/selectors/__init__.py
"""
Authentication Selectors Package.

All read-only DB operations for the authentication app.
Views and services consume selectors — never raw ORM directly.

Modules:
  user_selector.py    ← UserSelector class (get_by_email, get_by_phone, etc.)
  session_selector.py ← Session & LoginEvent selectors (Phase 5)

Usage:
    from apps.authentication.selectors import (
        UserSelector,
        get_active_sessions,
        get_login_events,
    )
"""

from apps.authentication.selectors.user_selector import UserSelector  # noqa: F401

# ── Session & Login Event selectors (Phase 5) ────────────────────────────────
from apps.authentication.selectors.session_selector import (  # noqa: F401
    get_active_sessions,
    get_login_events,
    get_login_events_for_ip,
    get_other_sessions,
    get_recent_failed_logins,
    get_session_by_id,
)

__all__ = [
    # User
    "UserSelector",
    # Session
    "get_active_sessions",
    "get_session_by_id",
    "get_other_sessions",
    # Login Events
    "get_login_events",
    "get_recent_failed_logins",
    "get_login_events_for_ip",
]
