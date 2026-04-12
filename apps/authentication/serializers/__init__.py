# apps/authentication/serializers/__init__.py
"""
Serializers package — backward-compatible re-exports.

ARCHITECTURE NOTE (Bug 9 — Phase 7):
  The original monolithic `serializers.py` (785 lines) has been split into
  domain-specific modules for maintainability and architectural consistency:

    serializers/
      auth.py      ← Login, Registration, Logout, TokenRefresh, GoogleAuth, OTP
      otp.py       ← ResendOTPRequestSerializer
      password.py  ← Reset Request/Confirm, PasswordChange
      profile.py   ← ProtectedUser, UserProfile, UserSerializer
      session.py   ← UserSession, LoginEvent (Phase 5 addition)

  This __init__.py re-exports EVERY serializer that was in the old file.
  All existing imports like:
      from apps.authentication.serializers import LoginSerializer
  continue to work WITHOUT any changes to views, tests, or other modules.
"""

# ── Auth / OTP ────────────────────────────────────────────────────────────────
from apps.authentication.serializers.auth import (  # noqa: F401
    GoogleAuthSerializer,
    LoginSerializer,
    LogoutSerializer,
    OTPSerializer,
    TokenRefreshSerializer,
    UserRegistrationSerializer,
)

# ── OTP Resend ────────────────────────────────────────────────────────────────
from apps.authentication.serializers.otp import (   # noqa: F401
    ResendOTPRequestSerializer,
)

# ── Password ──────────────────────────────────────────────────────────────────
from apps.authentication.serializers.password import (  # noqa: F401
    PasswordChangeSerializer,
    PasswordResetConfirmEmailSerializer,
    PasswordResetConfirmPhoneSerializer,
    PasswordResetRequestSerializer,
)

# ── Profile ───────────────────────────────────────────────────────────────────
from apps.authentication.serializers.profile import (  # noqa: F401
    ProtectedUserSerializer,
    UserProfileSerializer,
    UserSerializer,         # alias for UserProfileSerializer
)

# ── Session & Login Events (Phase 5) ─────────────────────────────────────────
from apps.authentication.serializers.session import (  # noqa: F401
    LoginEventListSerializer,
    LoginEventSerializer,
    SessionRevokeRequestSerializer,
    UserSessionListSerializer,
    UserSessionSerializer,
)

__all__ = [
    # Auth
    "OTPSerializer",
    "LoginSerializer",
    "UserRegistrationSerializer",
    "LogoutSerializer",
    "TokenRefreshSerializer",
    "GoogleAuthSerializer",
    # OTP
    "ResendOTPRequestSerializer",
    # Password
    "PasswordResetRequestSerializer",
    "PasswordResetConfirmEmailSerializer",
    "PasswordResetConfirmPhoneSerializer",
    "PasswordChangeSerializer",
    # Profile
    "ProtectedUserSerializer",
    "UserProfileSerializer",
    "UserSerializer",
    # Session & Login Events (Phase 5)
    "UserSessionSerializer",
    "UserSessionListSerializer",
    "SessionRevokeRequestSerializer",
    "LoginEventSerializer",
    "LoginEventListSerializer",
]
