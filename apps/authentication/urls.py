# apps/authentication/urls.py
"""
Authentication URLs - Synchronous & Asynchronous Routes

Architecture:
    v1/ - Synchronous endpoints (DRF GenericAPIView, WSGI-safe)
    v2/ - Asynchronous endpoints (Django Ninja, ASGI, high-concurrency)
"""

import logging
from django.urls import path
from apps.authentication.ninja_api import api 

# Sync views (DRF)
from apps.authentication.apis.auth_views.sync_views import (
    LoginView,
    RegisterView,
    LogoutView,
    RefreshTokenView,
    VerifyOTPView,
    ResendOTPView,
    GoogleAuthView
)
from apps.authentication.apis.password_views.sync_views import (
    PasswordResetRequestView,
    PasswordResetConfirmEmailView as PasswordResetConfirmView, # Alias mapping
    ChangePasswordView
)

logger = logging.getLogger('application')

app_name = 'authentication'

# ========================================================================
# V1 API - Synchronous Endpoints (Production-Ready, WSGI-Safe)
# ========================================================================

v1_auth_patterns = [
    path('v1/auth/login/', LoginView.as_view(), name='login-sync'),
    path('v1/auth/register/', RegisterView.as_view(), name='register-sync'),
    path('v1/auth/verify-otp/', VerifyOTPView.as_view(), name='verify-otp-sync'),
    path('v1/auth/resend-otp/', ResendOTPView.as_view(), name='resend-otp-sync'),
    path('v1/auth/google/', GoogleAuthView.as_view(), name='google-auth-sync'),
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

# Ninja manages its own routing tree.
# Mount the singleton NinjaAPI instance at v2/auth/.
v2_auth_patterns = [
    path('v2/auth/', api.urls),
]

urlpatterns = (
    v1_auth_patterns
    + v1_password_patterns
    + v2_auth_patterns
)

