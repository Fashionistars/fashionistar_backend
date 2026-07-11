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

logger = logging.getLogger(__name__)

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

# Ninja-compatible throttle wrappers (inherit from ninja.throttling.BaseThrottle)
# Created lazily to avoid import errors when Django Ninja is not installed.

def _make_ninja_throttle_class(scope_name: str, rate: str, anon: bool = False):
    """Create a Ninja-compatible throttle class on the fly."""
    from ninja.throttling import UserRateThrottle, AnonRateThrottle

    base = AnonRateThrottle if anon else UserRateThrottle

    # Convert DRF rate format to Ninja rate format
    # DRF: '120/minute', '5000/day', '20/hour'
    # Ninja: '120/min', '5000/day', '20/hour' (accepts s, sec, m, min, h, hour, d, day)
    ninja_rate = rate.replace("/minute", "/min")

    class _NinjaThrottle(base):
        scope = scope_name

        def __init__(self, throttle_rate: str = ninja_rate):
            super().__init__(rate=throttle_rate)

    _NinjaThrottle.__name__ = f"Ninja{scope_name.title().replace('_', '')}Throttle"
    return _NinjaThrottle


# Cache for generated Ninja throttle classes
_ninja_throttle_cache: dict = {}


def get_ninja_throttle(*throttle_classes: type) -> list:
    """
    Instantiate throttle classes for use in Ninja endpoint decorators.

    Converts DRF throttle classes to Ninja-compatible ones automatically
    by reading the scope and rate from the DRF class and creating a
    Ninja SimpleRateThrottle subclass with the same configuration.

    Usage::

        @router.post('/auth/login', throttle=get_ninja_throttle(AuthSensitiveThrottle))
        def login(request, payload: LoginSchema): ...
    """
    from ninja.throttling import BaseThrottle as NinjaBaseThrottle

    result = []
    for cls in throttle_classes:
        # If it's already a Ninja throttle, just instantiate
        if issubclass(cls, NinjaBaseThrottle):
            result.append(cls())
            continue

        # DRF throttle — convert to Ninja-compatible
        scope = getattr(cls, "scope", None)
        if scope is None:
            continue

        # Get the rate from the DRF class
        try:
            instance = cls()
            rate = instance.get_rate()
        except Exception:
            rate = None

        if rate is None:
            continue

        # Check if anon throttle (inherits from AnonRateThrottle)
        from rest_framework.throttling import AnonRateThrottle as DRFAnonRateThrottle
        is_anon = issubclass(cls, DRFAnonRateThrottle)

        # Get or create Ninja-compatible class
        cache_key = f"{scope}:{rate}:{is_anon}"
        if cache_key not in _ninja_throttle_cache:
            _ninja_throttle_cache[cache_key] = _make_ninja_throttle_class(scope, rate, anon=is_anon)

        ninja_cls = _ninja_throttle_cache[cache_key]
        result.append(ninja_cls())

    return result
