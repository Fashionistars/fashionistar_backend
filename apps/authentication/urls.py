# apps/authentication/urls.py
"""
Authentication URLs - Synchronous & Asynchronous Routes

Architecture:
    v1/ - Synchronous endpoints (DRF GenericAPIView, WSGI-safe)
    v2/ - Asynchronous endpoints (ADRF AsyncAPIView, ASGI, high-concurrency)
"""

import logging
from django.urls import path

# Sync views (DRF)
from apps.authentication.apis.auth_views.sync_views import (
    LoginView,
    RegisterView,
    LogoutView,
    RefreshTokenView
)
from apps.authentication.apis.password_views.sync_views import (
    PasswordResetRequestView,
    PasswordResetConfirmEmailView as PasswordResetConfirmView, # Alias mapping
    ChangePasswordView
)

# Async views (ADRF)
try:
    from apps.authentication.apis.auth_views.async_views import (
        AsyncLoginView,
        AsyncRegisterView,
        AsyncLogoutView,
        AsyncRefreshTokenView
    )
    from apps.authentication.apis.password_views.async_views import (
        PasswordResetRequestView as AsyncPasswordResetRequestView, # Mapping if class names differ
        PasswordResetConfirmEmailView as AsyncPasswordResetConfirmView,
        ChangePasswordView as AsyncChangePasswordView
    )
    ASYNC_VIEWS_AVAILABLE = True
except ImportError as e:
    ASYNC_VIEWS_AVAILABLE = False
    logger = logging.getLogger('application')
    logger.warning(
        f"❌ Async views not available: {e}. "
        "Using sync endpoints only."
    )

app_name = 'authentication'

# ========================================================================
# V1 API - Synchronous Endpoints (Production-Ready, WSGI-Safe)
# ========================================================================

v1_auth_patterns = [
    path('v1/auth/login/', LoginView.as_view(), name='login-sync'),
    path('v1/auth/register/', RegisterView.as_view(), name='register-sync'),
    path('v1/auth/logout/', LogoutView.as_view(), name='logout-sync'),
    path('v1/auth/token/refresh/', RefreshTokenView.as_view(), name='refresh-token-sync'),
]

v1_password_patterns = [
    path('v1/password/reset-request/', PasswordResetRequestView.as_view(), name='password-reset-request-sync'),
    path('v1/password/reset-confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm-sync'),
    path('v1/password/change/', ChangePasswordView.as_view(), name='password-change-sync'),
]

# ========================================================================
# V2 API - Asynchronous Endpoints (High-Concurrency, ASGI-Ready)
# ========================================================================

if ASYNC_VIEWS_AVAILABLE:
    v2_auth_patterns = [
        path('v2/auth/login/', AsyncLoginView.as_view(), name='login-async'),
        path('v2/auth/register/', AsyncRegisterView.as_view(), name='register-async'),
        path('v2/auth/logout/', AsyncLogoutView.as_view(), name='logout-async'),
        path('v2/auth/token/refresh/', AsyncRefreshTokenView.as_view(), name='refresh-token-async'),
    ]

    v2_password_patterns = [
        path('v2/password/reset-request/', AsyncPasswordResetRequestView.as_view(), name='password-reset-request-async'),
        path('v2/password/reset-confirm/', AsyncPasswordResetConfirmView.as_view(), name='password-reset-confirm-async'),
        path('v2/password/change/', AsyncChangePasswordView.as_view(), name='password-change-async'),
    ]
else:
    v2_auth_patterns = []
    v2_password_patterns = []

# ========================================================================
# Combined URL Patterns
# ========================================================================

urlpatterns = (
    v1_auth_patterns +
    v1_password_patterns +
    v2_auth_patterns +
    v2_password_patterns
)

# ========================================================================
# Legacy Endpoints (Backward Compatibility)
# ========================================================================
urlpatterns += [
    path('login/', LoginView.as_view(), name='login-legacy'),
    path('register/', RegisterView.as_view(), name='register-legacy'),
    path('logout/', LogoutView.as_view(), name='logout-legacy'),
    path('token/refresh/', RefreshTokenView.as_view(), name='refresh-token-legacy'),
    path('password-reset/', PasswordResetRequestView.as_view(), name='password-reset-request-legacy'),
    path('password-reset-confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm-legacy'),
    path('password-change/', ChangePasswordView.as_view(), name='password-change-legacy'),
]
