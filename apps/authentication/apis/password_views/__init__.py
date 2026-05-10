# apps/authentication/apis/password_views/__init__.py
"""
Password Views Package — Sync (DRF) only.

Async views deprecated (Phase 7). Re-introduce for async-specific endpoints later.
"""
from .sync_views import (  # noqa: F401
    PasswordResetRequestView,
    PasswordResetConfirmEmailView,
    PasswordResetConfirmPhoneView,
    ChangePasswordView,
)

__all__ = [
    'PasswordResetRequestView',
    'PasswordResetConfirmEmailView',
    'PasswordResetConfirmPhoneView',
    'ChangePasswordView',
]
