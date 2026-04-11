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

View Location Map:
    RegisterView, LoginView, VerifyOTPView, ResendOTPView,
    LogoutView, RefreshTokenView          → apis/auth_views/sync_views.py
    GoogleAuthView                        → apis/google_view/sync_views.py
    MeView, UserProfileDetailView         → apis/profile_views/sync_views.py
    PasswordReset*, ChangePasswordView    → apis/password_views/sync_views.py
    SessionListView, SessionRevokeView,
    SessionRevokeOthersView,
    LoginEventListView                    → apis/session_views/sync_views.py

Session ID Note:
    All model primary keys inherit from CommonTimestampModel which uses
    UUID7 (uuid_v7). Therefore session_id URL parameter is <str:session_id>
    NOT <int:session_id>.
"""

import logging
from django.urls import path
from apps.authentication.ninja_api import api

# ── Core Auth Views (Register, Login, OTP, Logout, Refresh) ──────────────────
from apps.authentication.apis.auth_views.sync_views import (
    LoginView,
    RegisterView,
    LogoutView,
    RefreshTokenView,
    VerifyOTPView,
    ResendOTPView,
)

# ── Google OAuth2 View (relocated from auth_views to dedicated package) ───────
from apps.authentication.apis.google_view.sync_views import (
    GoogleAuthView,
)

# ── Profile / Me View (relocated from auth_views to dedicated package) ────────
from apps.authentication.apis.profile_views.sync_views import (
    MeView,
    UserProfileDetailView,
    UserListView,
)

# ── Password Management Views ─────────────────────────────────────────────────
from apps.authentication.apis.password_views.sync_views import (
    PasswordResetRequestView,
    PasswordResetConfirmEmailView as PasswordResetConfirmView,   # Alias mapping
    PasswordResetConfirmPhoneView,
    ChangePasswordView,
)

# ── Session & Login Event Views (Security Dashboard) ─────────────────────────
from apps.authentication.apis.session_views.sync_views import (
    SessionListView,
    SessionRevokeView,
    SessionRevokeOthersView,
    LoginEventListView,
)

logger = logging.getLogger("application")

app_name = "authentication"

# ========================================================================
# V1 API - Core Auth Endpoints (Register, Login, OTP, Google, Logout)
# ========================================================================

v1_auth_patterns = [
    # GET  — Authenticated user profile (for Zustand rehydration on refresh)
    path("v1/auth/me/", MeView.as_view(), name="me-sync"),

    # POST — Email/Phone + Password → JWT tokens + user
    path("v1/auth/login/", LoginView.as_view(), name="login-sync"),

    # POST — Create new user account (email or phone + password + role)
    path("v1/auth/register/", RegisterView.as_view(), name="register-sync"),

    # POST — Verify OTP sent to email or phone after registration
    path("v1/auth/verify-otp/", VerifyOTPView.as_view(), name="verify-otp-sync"),

    # POST — Re-send OTP (throttled)
    path("v1/auth/resend-otp/", ResendOTPView.as_view(), name="resend-otp-sync"),

    # POST — Google OAuth2 ID-token → JWT tokens
    #        201 for new user (registration), 200 for returning user (login)
    path("v1/auth/google/", GoogleAuthView.as_view(), name="google-auth-sync"),

    # POST — Invalidate refresh token (logout from current device)
    path("v1/auth/logout/", LogoutView.as_view(), name="logout-sync"),

    # POST — Exchange refresh token → new access token (SimpleJWT)
    path(
        "v1/auth/token/refresh/", RefreshTokenView.as_view(), name="refresh-token-sync"
    ),
]

# ========================================================================
# V1 API - Profile Endpoints (GET/PATCH authenticated user profile)
# ========================================================================

v1_profile_patterns = [
    # GET/PATCH — Full user profile (includes phone, avatar, preferences)
    path("v1/profile/me/", UserProfileDetailView.as_view(), name="profile-detail-sync"),

    # GET — Admin: list all users
    path("v1/profile/users/", UserListView.as_view(), name="user-list-sync"),
]

# ========================================================================
# V1 API - Password Management
# ========================================================================

v1_password_patterns = [
    # POST — Request password reset (sends OTP email or SMS depending on identifier)
    path(
        "v1/password/reset-request/",
        PasswordResetRequestView.as_view(),
        name="password-reset-request-sync",
    ),
    # POST — Confirm email-based reset (uidb64 + token from email magic link)
    path(
        "v1/password/reset-confirm/<str:uidb64>/<str:token>/",
        PasswordResetConfirmView.as_view(),
        name="password-reset-confirm-sync",
    ),
    # POST — Confirm phone-based reset (OTP from SMS, no uidb64/token needed)
    path(
        "v1/password/reset-phone-confirm/",
        PasswordResetConfirmPhoneView.as_view(),
        name="password-reset-phone-confirm-sync",
    ),
    # POST — Change password (authenticated user, requires current_password)
    path(
        "v1/password/change/", ChangePasswordView.as_view(), name="password-change-sync"
    ),
]

# ── Security Dashboard — Telegram-style session & login-event management ─────
v1_session_patterns = [
    # GET  /api/v1/auth/sessions/           → list all active sessions for current user
    path(
        "v1/auth/sessions/",
        SessionListView.as_view(),
        name="session-list",
    ),
    # POST /api/v1/auth/sessions/revoke-others/  — logout all other devices
    # IMPORTANT: This must come BEFORE <str:session_id>/ to avoid being matched
    # by the wildcard. Django matches patterns top-to-bottom.
    path(
        "v1/auth/sessions/revoke-others/",
        SessionRevokeOthersView.as_view(),
        name="session-revoke-others",
    ),
    # DELETE /api/v1/auth/sessions/<uuid>/  → terminate one specific session
    # NOTE: session_id is UUID7 (string), NOT an integer.
    #       All models inherit from CommonTimestampModel with uuid_v7 primary key.
    path(
        "v1/auth/sessions/<str:session_id>/",
        SessionRevokeView.as_view(),
        name="session-revoke",
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
    + v1_profile_patterns
    + v1_password_patterns
    + v1_session_patterns
    + v1_ninja_patterns
)
