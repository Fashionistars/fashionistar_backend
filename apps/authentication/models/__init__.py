# apps/authentication/models/__init__.py
"""
Authentication Models Package
==============================

Split from the original monolithic ``models.py`` into domain-focused modules.
This ``__init__.py`` re-exports all models for backward-compatible imports:

    from apps.authentication.models import UnifiedUser
    from apps.authentication.models import MemberIDCounter, LoginEvent, UserSession

IMPORTANT: Uses RELATIVE imports so this package resolves correctly regardless
of how Django is invoked (uv run, manage.py, pytest, bash, PowerShell, etc.)
"""

# ── Core Identity ─────────────────────────────────────────────────────────────
from .unified_user import (  # noqa: F401
    UnifiedUser,
    MemberIDCounter,
    generate_member_id,
    MEMBER_ID_PREFIX,
    MEMBER_ID_DIGITS,
)

# ── Session & Events ─────────────────────────────────────────────────────────
from .user_session import UserSession          # noqa: F401
from .login_event import LoginEvent            # noqa: F401

# ── Biometrics ────────────────────────────────────────────────────────────────
from .biometric_credential import BiometricCredential  # noqa: F401

# ── Client Profile ────────────────────────────────────────────────────────────
from .client_profile import ClientProfile      # noqa: F401

__all__ = [
    # Core Identity
    "UnifiedUser",
    "MemberIDCounter",
    "generate_member_id",
    "MEMBER_ID_PREFIX",
    "MEMBER_ID_DIGITS",
    # Session & Events
    "UserSession",
    "LoginEvent",
    # Biometrics
    "BiometricCredential",
    # Profile
    "ClientProfile",
]
