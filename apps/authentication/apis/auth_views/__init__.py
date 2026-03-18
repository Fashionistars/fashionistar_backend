# apps/authentication/apis/auth_views/__init__.py
"""
Auth Views Package — Sync (DRF) only.

Note: Async Django-Ninja views have been deprecated (Phase 7).
      Only DRF sync views (sync_views.py) are active.
      Async views will be re-introduced for measurement/orders in a future phase.
"""
from .sync_views import (  # noqa: F401
    RegisterView as SyncRegisterView,
    LoginView as SyncLoginView,
    VerifyOTPView as SyncVerifyOTPView,
    ResendOTPView as SyncResendOTPView,
    GoogleAuthView as SyncGoogleAuthView,
    LogoutView as SyncLogoutView,
    RefreshTokenView as SyncRefreshTokenView,
)

__all__ = [
    # Sync (DRF) — active
    'SyncRegisterView', 'SyncLoginView', 'SyncVerifyOTPView',
    'SyncResendOTPView', 'SyncGoogleAuthView', 'SyncLogoutView',
    'SyncRefreshTokenView',
]
