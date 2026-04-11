# apps/authentication/apis/auth_views/__init__.py
"""
Auth Views Package — Sync (DRF) only.

Note: Async Django-Ninja views have been deprecated (Phase 7).
      Only DRF sync views (sync_views.py) are active.

Note: GoogleAuthView has been relocated to → apis/google_view/sync_views.py
      MeView has been relocated to          → apis/profile_views/sync_views.py
"""
from .sync_views import (  # noqa: F401
    RegisterView as SyncRegisterView,
    LoginView as SyncLoginView,
    VerifyOTPView as SyncVerifyOTPView,
    ResendOTPView as SyncResendOTPView,
    LogoutView as SyncLogoutView,
    RefreshTokenView as SyncRefreshTokenView,
)

__all__ = [
    # Sync (DRF) — active
    'SyncRegisterView', 'SyncLoginView', 'SyncVerifyOTPView',
    'SyncResendOTPView', 'SyncLogoutView', 'SyncRefreshTokenView',
]
