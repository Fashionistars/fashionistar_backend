# apps/authentication/models/user_session.py
"""
UserSession Model — Active Session Registry With Revocation Metadata
====================================================================

One row represents one issued refresh token family/session. Active-session
dashboards read from the default manager; revoked rows remain available through
``all_objects`` for audit, admin, and compliance workflows.
"""

from __future__ import annotations

import datetime
import hashlib

from django.db import models
from django.utils import timezone

from apps.common.models import TimeStampedModel


class UserSessionQuerySet(models.QuerySet):
    """Custom queryset helpers for active and revoked session views."""

    def active(self):
        """Return only non-revoked sessions."""

        return self.filter(revoked_at__isnull=True)

    def revoked(self):
        """Return only revoked sessions."""

        return self.filter(revoked_at__isnull=False)


class ActiveUserSessionManager(models.Manager):
    """Default manager that hides revoked rows from app-facing queries."""

    def get_queryset(self):
        return UserSessionQuerySet(self.model, using=self._db).active()


class UserSession(TimeStampedModel):
    """
    Tracks every authenticated refresh-token session for a user.

    Default behavior:
      - ``objects`` exposes only active sessions.
      - ``all_objects`` exposes the full append-only registry.

    This keeps user-facing security dashboards clean while preserving enough
    history for audit review, admin operations, and incident response.
    """

    CLIENT_WEB = "web"
    CLIENT_MOBILE = "mobile"
    CLIENT_API = "api"
    CLIENT_UNKNOWN = "unknown"

    CLIENT_TYPE_CHOICES = [
        (CLIENT_WEB, "Web Browser"),
        (CLIENT_MOBILE, "Mobile App"),
        (CLIENT_API, "API Client"),
        (CLIENT_UNKNOWN, "Unknown"),
    ]

    user = models.ForeignKey(
        "authentication.UnifiedUser",
        on_delete=models.CASCADE,
        related_name="sessions",
        db_index=True,
        help_text="The owner of this session.",
    )
    jti = models.CharField(
        max_length=255,
        unique=True,
        db_index=True,
        help_text=(
            "JWT ID (jti claim) of the refresh token for this session. "
            "Used to match and blacklist via SimpleJWT."
        ),
    )
    refresh_token_family = models.CharField(
        max_length=255,
        blank=True,
        db_index=True,
        help_text=(
            "Stable family identifier for rotated refresh tokens when available. "
            "Falls back to the refresh token JTI for legacy tokens."
        ),
    )
    fingerprint_hash = models.CharField(
        max_length=128,
        blank=True,
        db_index=True,
        help_text=(
            "SHA-256 hash derived from IP and User-Agent for coarse device "
            "fingerprinting without storing only raw identifiers."
        ),
    )

    client_type = models.CharField(
        max_length=20,
        choices=CLIENT_TYPE_CHOICES,
        default=CLIENT_UNKNOWN,
        help_text="Browser / mobile app / API client.",
    )
    browser_family = models.CharField(
        max_length=100,
        blank=True,
        help_text="Chrome, Firefox, Safari, and other browser families.",
    )
    os_family = models.CharField(
        max_length=100,
        blank=True,
        help_text="Windows, macOS, iOS, Android, Linux, and similar platforms.",
    )
    device_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Human-readable label such as 'Chrome on Windows'.",
    )
    user_agent = models.TextField(blank=True, help_text="Raw login-time User-Agent string.")

    ip_address = models.GenericIPAddressField(
        protocol="both",
        unpack_ipv4=True,
        null=True,
        blank=True,
        help_text="IP address captured at session creation time.",
    )
    last_seen_ip = models.GenericIPAddressField(
        protocol="both",
        unpack_ipv4=True,
        null=True,
        blank=True,
        help_text="Most recent IP address observed for this session.",
    )
    country = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=3, blank=True)
    city = models.CharField(max_length=100, blank=True)

    last_seen_user_agent = models.TextField(
        blank=True,
        help_text="Most recent User-Agent observed for this session.",
    )
    last_used_at = models.DateTimeField(
        auto_now=True,
        help_text="Updated when the session is refreshed or otherwise reused.",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the refresh token expires.",
    )
    revoked_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Timestamp when the session was explicitly revoked.",
    )
    revoked_reason = models.CharField(
        max_length=255,
        blank=True,
        help_text="Operator-facing reason for revoking the session.",
    )
    is_current = models.BooleanField(
        default=False,
        help_text=(
            "Frontend-only convenience flag. The API computes this at serializer "
            "time and does not rely on the stored database value."
        ),
    )

    objects = ActiveUserSessionManager()
    all_objects = UserSessionQuerySet.as_manager()

    class Meta:
        verbose_name = "User Session"
        verbose_name_plural = "User Sessions"
        ordering = ["-last_used_at"]
        indexes = [
            models.Index(fields=["user", "-last_used_at"], name="us_user_ts_idx"),
            models.Index(fields=["jti"], name="us_jti_idx"),
            models.Index(fields=["expires_at"], name="us_expires_idx"),
            models.Index(fields=["revoked_at"], name="us_revoked_idx"),
            models.Index(fields=["refresh_token_family"], name="us_family_idx"),
            models.Index(fields=["fingerprint_hash"], name="us_fprint_idx"),
        ]

    def __str__(self):
        status = "revoked" if self.is_revoked else "active"
        location = self.city or self.country or self.ip_address or "?"
        return f"{self.user} — {self.device_name or self.client_type} ({location}) [{status}]"

    @property
    def is_revoked(self) -> bool:
        """Return True when the session has been revoked."""

        return self.revoked_at is not None

    @staticmethod
    def _extract_client_details(request) -> tuple[str | None, str]:
        """Extract best-effort IP and User-Agent details from a request."""

        ip_address = None
        user_agent = ""
        if request is None:
            return ip_address, user_agent

        forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
        ip_address = (
            forwarded.split(",")[0].strip()
            if forwarded
            else request.META.get("REMOTE_ADDR")
        )
        user_agent = request.META.get("HTTP_USER_AGENT", "")
        return ip_address, user_agent

    @staticmethod
    def _build_fingerprint(user_agent: str, ip_address: str | None) -> str:
        """Hash the most stable device hints into a privacy-safer fingerprint."""

        seed = f"{ip_address or ''}|{user_agent or ''}".strip("|")
        if not seed:
            return ""
        return hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def revoke(self, *, reason: str = "") -> bool:
        """
        Mark the session as revoked without deleting the row.

        Returns:
            bool: True when the row transitioned from active to revoked,
            False when it had already been revoked.
        """

        revoked_at = timezone.now()
        updated = self.__class__.all_objects.filter(
            pk=self.pk,
            revoked_at__isnull=True,
        ).update(
            revoked_at=revoked_at,
            revoked_reason=(reason or self.revoked_reason or "").strip(),
        )
        if not updated:
            return False

        self.revoked_at = revoked_at
        self.revoked_reason = (reason or self.revoked_reason or "").strip()
        return True

    @classmethod
    def create_from_token(
        cls,
        *,
        user,
        refresh_token,
        request=None,
    ) -> "UserSession":
        """
        Create a new session record from a SimpleJWT ``RefreshToken`` instance.

        Called after a successful login or verification flow. The method stores
        device metadata, token expiry, and a coarse fingerprint for later
        security review.
        """

        ip_address, user_agent = cls._extract_client_details(request)

        jti = str(refresh_token.payload.get("jti", ""))
        refresh_token_family = str(
            refresh_token.payload.get("family")
            or refresh_token.payload.get("refresh_token_family")
            or jti
        )
        expires_at = timezone.now() + datetime.timedelta(
            seconds=int(refresh_token.lifetime.total_seconds())
        )

        device_name = "Unknown Device"
        browser_family = ""
        os_family = ""
        try:
            import user_agents as ua_parser

            ua = ua_parser.parse(user_agent)
            browser_family = ua.browser.family
            os_family = ua.os.family
            device_name = (
                f"{browser_family} on {os_family}"
                if browser_family and browser_family != "Other"
                else (os_family or device_name)
            )
        except Exception:
            pass

        return cls.objects.create(
            user=user,
            jti=jti,
            refresh_token_family=refresh_token_family,
            fingerprint_hash=cls._build_fingerprint(user_agent, ip_address),
            user_agent=user_agent,
            last_seen_user_agent=user_agent,
            device_name=device_name,
            browser_family=browser_family,
            os_family=os_family,
            ip_address=ip_address,
            last_seen_ip=ip_address,
            expires_at=expires_at,
        )
