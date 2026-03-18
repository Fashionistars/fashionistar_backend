# apps/authentication/apis/profile_views/__init__.py
"""
Profile Views Package — Sync (DRF) only.

Async profile views deprecated (Phase 7).
"""
from .sync_views import (  # noqa: F401
    ProtectedUserView,
    UserProfileView,
)

__all__ = [
    'ProtectedUserView',
    'UserProfileView',
]
