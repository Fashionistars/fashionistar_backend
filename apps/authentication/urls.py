# apps/authentication/urls.py
"""
Authentication URLs — Synchronous & Asynchronous Routes

Architecture:
    /api/v1/auth/         — Synchronous DRF endpoints (WSGI-safe, production)
    /api/v1/ninja/auth/   — Asynchronous Django Ninja endpoints (ASGI, high-concurrency)

Versioning Rule:
    All endpoints — both DRF and Ninja — are version 1 (v1).
    Future versions will be added under /api/v2/ when breaking changes are needed.
    Ninja uses the dedicated /api/v1/ninja/ prefix to avoid URL collisions with DRF.
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
    GoogleAuthView,
)
from apps.authentication.apis.password_views.sync_views import (
    PasswordResetRequestView,
    PasswordResetConfirmEmailView as PasswordResetConfirmView,  # Alias mapping
    PasswordResetConfirmPhoneView,
    ChangePasswordView,
)
from apps.authentication.apis.session_views.sync_views import (
    SessionListView,
    SessionRevokeView,
    SessionRevokeOthersView,
    LoginEventListView,
)

logger = logging.getLogger("application")

app_name = "authentication"

# ========================================================================
# V1 API - Synchronous Endpoints (Production-Ready, WSGI-Safe)
# ========================================================================

v1_auth_patterns = [
    path("v1/auth/login/", LoginView.as_view(), name="login-sync"),
    path("v1/auth/register/", RegisterView.as_view(), name="register-sync"),
    path("v1/auth/verify-otp/", VerifyOTPView.as_view(), name="verify-otp-sync"),
    path("v1/auth/resend-otp/", ResendOTPView.as_view(), name="resend-otp-sync"),
    path("v1/auth/google/", GoogleAuthView.as_view(), name="google-auth-sync"),
    path("v1/auth/logout/", LogoutView.as_view(), name="logout-sync"),
    path(
        "v1/auth/token/refresh/", RefreshTokenView.as_view(), name="refresh-token-sync"
    ),
]

v1_password_patterns = [
    path(
        "v1/password/reset-request/",
        PasswordResetRequestView.as_view(),
        name="password-reset-request-sync",
    ),
    path(
        "v1/password/reset-confirm/<str:uidb64>/<str:token>/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm-sync",
    ),
    path(
        "v1/password/reset-phone-confirm/",
        PasswordResetConfirmPhoneView.as_view(),
        name="password-reset-phone-confirm-sync",
    ),
    path(
        "v1/password/change/", ChangePasswordView.as_view(), name="password-change-sync"
    ),
]

# ── Security Dashboard — Telegram-style session & login-event management ──
v1_session_patterns = [
    # GET  /api/v1/auth/sessions/           → list all active sessions
    path(
        "v1/auth/sessions/",
        SessionListView.as_view(),
        name="session-list",
    ),
    # DELETE /api/v1/auth/sessions/<id>/    → terminate one specific session
    path(
        "v1/auth/sessions/<int:session_id>/",
        SessionRevokeView.as_view(),
        name="session-revoke",
    ),
    # POST /api/v1/auth/sessions/revoke-others/  → logout all other devices
    path(
        "v1/auth/sessions/revoke-others/",
        SessionRevokeOthersView.as_view(),
        name="session-revoke-others",
    ),
    # GET  /api/v1/auth/login-events/       → Binance-style login audit log
    path(
        "v1/auth/login-events/",
        LoginEventListView.as_view(),
        name="login-events",
    ),
]

# ========================================================================
# V1 Ninja API — Asynchronous Endpoints (High-Concurrency, ASGI-Ready)
# ========================================================================
# All Ninja endpoints MUST be mounted under /api/v1/ninja/ to:
#   1. Stay on v1 (uniform versioning across the whole API)
#   2. Avoid URL collisions with DRF v1 endpoints at /api/v1/auth/
#   3. Make versioning explicit: /api/v1/ninja/auth/*, /api/v1/ninja/products/*, etc.
v1_ninja_patterns = [
    path("v1/ninja/auth/", api.urls),
]

urlpatterns = (
    v1_auth_patterns
    + v1_password_patterns
    + v1_session_patterns
    + v1_ninja_patterns
)

