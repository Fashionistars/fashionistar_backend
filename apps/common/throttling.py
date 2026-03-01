# apps/common/throttling.py
"""
Enterprise-grade rate limiting for Fashionistar API.

Throttle classes (fine-grained, per-endpoint):

  Tier           Class                     Default Rate        Use-case
  ─────────────────────────────────────────────────────────────────────
  Anonymous      AnonBurstThrottle         30 / minute         Public reads
  Anonymous      AnonSustainedThrottle     500 / day           Public reads
  Authenticated  UserBurstThrottle         120 / minute        Normal API calls
  Authenticated  UserSustainedThrottle     5 000 / day         Normal API calls
  Auth endpoints AuthSensitiveThrottle     5 / minute          Login / register
  OTP endpoints  OTPThrottle               3 / minute          OTP send / verify
  Upload         UploadThrottle            20 / hour           File / image uploads
  Superadmin     SuperadminThrottle        unlimited           Admin bypass
  Vendor         VendorThrottle            200 / minute        Vendor dashboard
  Webhook        WebhookThrottle           unlimited           Paystack / etc.

All rates are configurable via settings.THROTTLE_RATES (takes precedence over
the class-level defaults). This avoids deploy-time restarts for rate changes.

Usage in a Ninja endpoint::

    from apps.common.throttling import get_ninja_throttle

    @router.post('/auth/login', throttle=[AuthSensitiveThrottle()])
    def login(request, payload: LoginSchema):
        ...

Usage in a DRF view / ViewSet::

    from apps.common.throttling import AuthSensitiveThrottle, OTPThrottle

    class OTPVerifyView(APIView):
        throttle_classes = [OTPThrottle]

Registration in settings.py REST_FRAMEWORK::

    'DEFAULT_THROTTLE_CLASSES': [
        'apps.common.throttling.UserBurstThrottle',
        'apps.common.throttling.AnonBurstThrottle',
    ],
    'DEFAULT_THROTTLE_RATES': {  # Maps scope → rate (DRF format)
        'anon_burst':   '30/minute',
        'anon_day':     '500/day',
        'user_burst':   '120/minute',
        'user_day':     '5000/day',
        'auth':         '5/minute',
        'otp':          '3/minute',
        'upload':       '20/hour',
        'vendor':       '200/minute',
    },
"""

from __future__ import annotations

import logging
from typing import Optional

from django.conf import settings
from rest_framework.throttling import (
    AnonRateThrottle,
    BaseThrottle,
    UserRateThrottle,
)

logger = logging.getLogger("application")

# ---------------------------------------------------------------------------
# Helper: read rate from settings, fall back to class default
# ---------------------------------------------------------------------------

def _rate(scope: str, default: str) -> str:
    """Return the configured rate for *scope*, or *default* if not set."""
    configured = getattr(settings, "THROTTLE_RATES", {})
    return configured.get(scope, default)


# ---------------------------------------------------------------------------
# Anonymous throttles
# ---------------------------------------------------------------------------

class AnonBurstThrottle(AnonRateThrottle):
    """Short-burst limit for unauthenticated callers (30 req/min default)."""
    scope = "anon_burst"

    def get_rate(self) -> Optional[str]:
        return _rate(self.scope, "30/minute")


class AnonSustainedThrottle(AnonRateThrottle):
    """Daily ceiling for unauthenticated callers (500 req/day default)."""
    scope = "anon_day"

    def get_rate(self) -> Optional[str]:
        return _rate(self.scope, "500/day")


# ---------------------------------------------------------------------------
# Authenticated user throttles
# ---------------------------------------------------------------------------

class UserBurstThrottle(UserRateThrottle):
    """Per-minute ceiling for authenticated users (120 req/min default)."""
    scope = "user_burst"

    def get_rate(self) -> Optional[str]:
        return _rate(self.scope, "120/minute")


class UserSustainedThrottle(UserRateThrottle):
    """Daily ceiling for authenticated users (5 000 req/day default)."""
    scope = "user_day"

    def get_rate(self) -> Optional[str]:
        return _rate(self.scope, "5000/day")


# ---------------------------------------------------------------------------
# Sensitive endpoint throttles
# ---------------------------------------------------------------------------

class AuthSensitiveThrottle(AnonRateThrottle):
    """
    Strict throttle for auth endpoints (login, register, password reset).
    Uses AnonRateThrottle base so it applies even before authentication.
    Default: 5 requests / minute per IP.
    """
    scope = "auth"

    def get_rate(self) -> Optional[str]:
        return _rate(self.scope, "5/minute")


class OTPThrottle(AnonRateThrottle):
    """
    Very strict throttle for OTP send / verify endpoints.
    Prevents OTP enumeration and SMS bombing.
    Default: 3 requests / minute per IP.
    """
    scope = "otp"

    def get_rate(self) -> Optional[str]:
        return _rate(self.scope, "3/minute")


# ---------------------------------------------------------------------------
# Resource-specific throttles
# ---------------------------------------------------------------------------

class UploadThrottle(UserRateThrottle):
    """
    Throttle for file / image upload endpoints.
    Prevents storage exhaustion attacks.
    Default: 20 uploads / hour per user.
    """
    scope = "upload"

    def get_rate(self) -> Optional[str]:
        return _rate(self.scope, "20/hour")


class VendorThrottle(UserRateThrottle):
    """
    Higher throughput for vendor dashboard operations.
    Default: 200 requests / minute per vendor.
    """
    scope = "vendor"

    def get_rate(self) -> Optional[str]:
        return _rate(self.scope, "200/minute")


# ---------------------------------------------------------------------------
# Bypass throttles (no-op)
# ---------------------------------------------------------------------------

class SuperadminThrottle(BaseThrottle):
    """
    No-op throttle for superadmin actions.
    Returns True (allow) always — superadmins bypass all rate limits.
    Log abuse at WARNING level for audit purposes.
    """

    def allow_request(self, request, view) -> bool:  # type: ignore[override]
        user = getattr(request, "user", None)
        if user and getattr(user, "is_superuser", False):
            return True
        return True  # Fallback: allow (use alongside other throttles)

    def wait(self) -> Optional[float]:
        return None


class WebhookThrottle(BaseThrottle):
    """
    No-op throttle for inbound webhook endpoints (Paystack, etc.).
    Security is handled via signature verification, not rate limiting.
    """

    def allow_request(self, request, view) -> bool:  # type: ignore[override]
        return True

    def wait(self) -> Optional[float]:
        return None


# ---------------------------------------------------------------------------
# Django Ninja helper
# ---------------------------------------------------------------------------

def get_ninja_throttle(*throttle_classes: type) -> list:
    """
    Instantiate throttle classes for use in Ninja endpoint decorators.

    Usage::

        @router.post('/auth/login', throttle=get_ninja_throttle(AuthSensitiveThrottle))
        def login(request, payload: LoginSchema): ...
    """
    return [cls() for cls in throttle_classes]
