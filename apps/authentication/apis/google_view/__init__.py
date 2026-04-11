# apps/authentication/apis/google_view/__init__.py
"""
Google Auth Views Package — Sync (DRF) only.

Contains GoogleAuthView which handles POST /api/v1/auth/google/
for Google OAuth2 ID-token verification and JWT issuance.
"""
from .sync_views import GoogleAuthView  # noqa: F401

__all__ = ['GoogleAuthView']
