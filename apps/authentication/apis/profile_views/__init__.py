# apps/authentication/apis/profile_views/__init__.py
"""
Profile Views Package — Sync (DRF) only.

Exports:
  - UserProfileDetailView : GET/PATCH /api/v1/profile/me/   (authenticated user)
  - UserListView          : GET /api/v1/profile/users/      (admin only)
  - MeView                : GET /api/v1/auth/me/            (lightweight auth rehydration)
"""
from .sync_views import (  # noqa: F401
    UserProfileDetailView,
    UserListView,
    MeView,
)

__all__ = [
    'UserProfileDetailView',
    'UserListView',
    'MeView',
]
