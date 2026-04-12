# apps/authentication/models/__init__.py
"""
Authentication Models Package — Split Structure (Phase 5)
=========================================================

Models are split from the monolithic ``models.py`` (1179 lines) into
individual files for maintainability and architectural clarity.

Model → File mapping:
  UnifiedUser          → unified_user.py
  MemberIDCounter      → unified_user.py (helper for member_id generation)
  BiometricCredential  → biometric_credential.py
  LoginEvent           → login_event.py
  UserSession          → user_session.py
  ClientProfile        → client_profile.py

All existing imports remain IDENTICAL:
    from apps.authentication.models import UnifiedUser
    from apps.authentication.models import LoginEvent, UserSession
    from apps.authentication.models import ClientProfile

Django migration history is NOT affected — models still live in the
``authentication`` app. The ``db_table`` Meta attributes are preserved.

IMPORTANT: The top-level ``models.py`` (the original monolith) is kept
as a thin redirect that re-imports from here, ensuring zero migration drift.
"""

# ── Core User ─────────────────────────────────────────────────────────────────
from apps.authentication.models.unified_user import (  # noqa: F401
    UnifiedUser,
    MemberIDCounter,
    generate_member_id,
    MEMBER_ID_PREFIX,
    MEMBER_ID_DIGITS,
)

# ── Biometric ─────────────────────────────────────────────────────────────────
from apps.authentication.models.biometric_credential import (  # noqa: F401
    BiometricCredential,
)

# ── Audit / Security ──────────────────────────────────────────────────────────
from apps.authentication.models.login_event import (  # noqa: F401
    LoginEvent,
)

from apps.authentication.models.user_session import (  # noqa: F401
    UserSession,
)

# ── Profiles ──────────────────────────────────────────────────────────────────
from apps.authentication.models.client_profile import (  # noqa: F401
    ClientProfile,
)

__all__ = [
    # Core
    "UnifiedUser",
    "MemberIDCounter",
    "generate_member_id",
    "MEMBER_ID_PREFIX",
    "MEMBER_ID_DIGITS",
    # Biometric
    "BiometricCredential",
    # Audit
    "LoginEvent",
    "UserSession",
    # Profiles
    "ClientProfile",
]
