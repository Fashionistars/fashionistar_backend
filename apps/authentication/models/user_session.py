# apps/authentication/models/user_session.py
"""
UserSession Model — Telegram-style Active Sessions Registry
===========================================================

One row per live refresh token. "Active sessions" dashboard
reads from this table. "Log out all other devices" deletes rows.

Import:
    from apps.authentication.models import UserSession
"""

from apps.common.models import TimeStampedModel
from django.db import models


class UserSession(TimeStampedModel):
    """
    Tracks every active **authenticated session** (one per refresh token).

    This is the SERVER-SIDE session registry — conceptually similar to
    Telegram's "Active Sessions", GitHub's "Sessions", or Google's
    "Devices this account is signed in to".

    Key capabilities enabled by this model:
      1. **Enumerate active sessions** — ``GET /api/v1/auth/sessions/``
         returns all of the user's live sessions: device, location, last-used.
      2. **Revoke a specific session** — ``DELETE /api/v1/auth/sessions/{<uuid> session_id}/``
         deletes the row AND blacklists the JWT refresh token.
      3. **Logout all other devices** — ``POST /api/v1/auth/sessions/revoke-others/``
         deletes all rows except the current one AND blacklists all their tokens.

    Session lifecycle:
      created:    at successful login / Google OAuth / OTP verification
      refreshed:  ``last_used_at`` updated on every token refresh call
      terminated: deleted on explicit logout OR when the refresh token expires
    """

    # ── Device / client types ─────────────────────────────────────────
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

    # ── Core ──────────────────────────────────────────────────────────
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

    # ── Device information ────────────────────────────────────────────
    client_type = models.CharField(
        max_length=20,
        choices=CLIENT_TYPE_CHOICES,
        default=CLIENT_UNKNOWN,
        help_text="Browser / mobile app / API client.",
    )
    browser_family = models.CharField(
        max_length=100, blank=True, help_text="Chrome, Firefox, Safari, etc."
    )
    os_family = models.CharField(
        max_length=100,
        blank=True,
        help_text="Windows, macOS, iOS, Android, Linux, etc.",
    )
    device_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Human-readable label, e.g. 'Chrome on Windows', 'iPhone 15 Pro Max'.",
    )
    user_agent = models.TextField(blank=True, help_text="Raw User-Agent string.")

    # ── Geolocation ───────────────────────────────────────────────────
    ip_address = models.GenericIPAddressField(
        protocol="both",
        unpack_ipv4=True,
        null=True,
        blank=True,
        help_text="IP address at session creation (login time).",
    )
    country = models.CharField(max_length=100, blank=True)
    country_code = models.CharField(max_length=3, blank=True)
    city = models.CharField(max_length=100, blank=True)

    # ── Activity ──────────────────────────────────────────────────────
    last_used_at = models.DateTimeField(
        auto_now=True,
        help_text="Updated on every token refresh. Stale sessions = last_used_at old.",
    )
    expires_at = models.DateTimeField(
        null=True,
        blank=True,
        help_text="When the refresh token expires (from JWT payload).",
    )
    is_current = models.BooleanField(
        default=False,
        help_text=(
            "True for the session that corresponds to the JWT making "
            "the current request. Computed at serializer time, not stored."
        ),
    )

    class Meta:
        verbose_name = "User Session"
        verbose_name_plural = "User Sessions"
        ordering = ["-last_used_at"]
        indexes = [
            models.Index(fields=["user", "-last_used_at"], name="us_user_ts_idx"),
            models.Index(fields=["jti"], name="us_jti_idx"),
            models.Index(fields=["expires_at"], name="us_expires_idx"),
        ]

    def __str__(self):
        return (
            f"{self.user} — {self.device_name or self.client_type} "
            f"({self.city or self.country or self.ip_address or '?'})"
        )

    @classmethod
    def create_from_token(
        cls,
        *,
        user,
        refresh_token,
        request=None,
    ) -> "UserSession":
        """
        Create a new session record from a SimpleJWT RefreshToken instance.

        Called immediately after a successful login / Google OAuth / OTP
        verification. IP and User-Agent are extracted from the request.

        Args:
            user:           The authenticated UnifiedUser.
            refresh_token:  A ``rest_framework_simplejwt.tokens.RefreshToken``
                            instance (already issued).
            request:        The Django HttpRequest (for IP + User-Agent).

        Returns:
            The newly-created ``UserSession`` instance.
        """
        import datetime
        from django.utils import timezone

        ip_address = None
        user_agent = ""
        if request:
            forwarded = request.META.get("HTTP_X_FORWARDED_FOR")
            ip_address = (
                forwarded.split(",")[0].strip()
                if forwarded
                else request.META.get("REMOTE_ADDR")
            )
            user_agent = request.META.get("HTTP_USER_AGENT", "")

        jti = str(refresh_token.payload.get("jti", ""))
        expires_at = timezone.now() + datetime.timedelta(
            seconds=int(refresh_token.lifetime.total_seconds())
        )

        # Build a readable device label from User-Agent
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
                if browser_family != "Other"
                else os_family
            )
        except Exception:
            pass

        return cls.objects.create(
            user=user,
            jti=jti,
            user_agent=user_agent,
            device_name=device_name,
            browser_family=browser_family,
            os_family=os_family,
            ip_address=ip_address,
            expires_at=expires_at,
        )
