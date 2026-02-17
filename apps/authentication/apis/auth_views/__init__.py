# apps/authentication/apis/auth_views/__init__.py
"""
Auth Views Package — Sync (DRF) + Async (Ninja/ADRF).

Sync views:  RegisterView, LoginView, VerifyOTPView, etc.
Async views: auth_router (Ninja), AsyncLoginView (ADRF), etc.
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
from .async_views import (  # noqa: F401
    auth_router,
    AsyncLoginView,
    AsyncLogoutView,
    AsyncRefreshTokenView,
    VerifyOTPView as AsyncVerifyOTPView,
)

__all__ = [
    # Sync (DRF)
    'SyncRegisterView', 'SyncLoginView', 'SyncVerifyOTPView',
    'SyncResendOTPView', 'SyncGoogleAuthView', 'SyncLogoutView',
    'SyncRefreshTokenView',
    # Async (Ninja Router + ADRF)
    'auth_router',
    'AsyncLoginView', 'AsyncLogoutView', 'AsyncRefreshTokenView',
    'AsyncVerifyOTPView',
]

