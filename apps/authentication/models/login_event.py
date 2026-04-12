# apps/authentication/models/login_event.py
"""
LoginEvent Model — Binance-style Security Audit Log
===================================================

Every login attempt (success OR failure) is recorded here.
Displayed as "Recent Login Activity" in the user Security Dashboard.

Import:
    from apps.authentication.models import LoginEvent
"""

from apps.common.models import TimeStampedModel
from django.db import models


class LoginEvent(TimeStampedModel):
    """
    Immutable security audit record for every login **attempt**.

    Modelled after the security audit logs used by Binance, Coinbase,
    Telegram, and Google — capturing the minimum viable set of forensic
    data needed for:
      - User-visible "recent logins" in the Security Dashboard
      - SIEM / threat-detection pipelines
      - Suspicious-activity alerting (new country, new device, etc.)
      - Compliance and audit trails

    Design decisions:
      - ``user`` is nullable so we can log failed attempts for
        *unknown* identifiers (user enumeration attempts).
      - ``is_successful`` + ``failure_reason`` let us distinguish
        wrong-password from inactive-account from deactivated-account
        in a single table scan.
      - ``risk_score`` (0–100) is updated by a Celery task after
        the request completes (geo-lookup + device fingerprint).
      - ``ip_address`` uses ``GenericIPAddressField`` to support both
        IPv4 and IPv6 natively.
      - The model is intentionally **append-only** — no update() calls.
        Audit records must never be mutated.
    """

    # ── Outcomes ─────────────────────────────────────────────────────
    OUTCOME_SUCCESS    = 'success'
    OUTCOME_FAILED     = 'failed'
    OUTCOME_BLOCKED    = 'blocked'      # IP-banned or rate-limited
    OUTCOME_SUSPICIOUS = 'suspicious'   # MFA challenged

    OUTCOME_CHOICES = [
        (OUTCOME_SUCCESS,    'Success'),
        (OUTCOME_FAILED,     'Failed'),
        (OUTCOME_BLOCKED,    'Blocked'),
        (OUTCOME_SUSPICIOUS, 'Suspicious'),
    ]

    # ── Device / client types ─────────────────────────────────────────
    CLIENT_WEB     = 'web'
    CLIENT_MOBILE  = 'mobile'
    CLIENT_API     = 'api'
    CLIENT_CURL    = 'curl'
    CLIENT_UNKNOWN = 'unknown'

    CLIENT_TYPE_CHOICES = [
        (CLIENT_WEB,     'Web Browser'),
        (CLIENT_MOBILE,  'Mobile App'),
        (CLIENT_API,     'API Client'),
        (CLIENT_CURL,    'cURL / Script'),
        (CLIENT_UNKNOWN, 'Unknown'),
    ]

    # ── Auth methods ──────────────────────────────────────────────────
    METHOD_EMAIL     = 'email'
    METHOD_PHONE     = 'phone'
    METHOD_GOOGLE    = 'google'
    METHOD_BIOMETRIC = 'biometric'

    METHOD_CHOICES = [
        (METHOD_EMAIL,     'Email + Password'),
        (METHOD_PHONE,     'Phone + Password'),
        (METHOD_GOOGLE,    'Google OAuth'),
        (METHOD_BIOMETRIC, 'Biometric / FIDO2'),
    ]

    # ── Core relations ───────────────────────────────────────────────
    user = models.ForeignKey(
        "authentication.UnifiedUser",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name='login_events',
        db_index=True,
        help_text=(
            "NULL when a login attempt targets an unknown identifier "
            "(failed user-enumeration attempt)."
        ),
    )

    # ── Request metadata ──────────────────────────────────────────────
    ip_address = models.GenericIPAddressField(
        protocol='both',
        unpack_ipv4=True,
        db_index=True,
        help_text="Client IP address (supports IPv4 and IPv6).",
    )
    user_agent = models.TextField(
        blank=True,
        help_text="Raw HTTP User-Agent string.",
    )

    # ── Parsed device info ─────────────────────────────────────────────
    client_type = models.CharField(
        max_length=20,
        choices=CLIENT_TYPE_CHOICES,
        default=CLIENT_UNKNOWN,
        db_index=True,
        help_text="Derived from User-Agent: web / mobile / api / curl.",
    )
    browser_family = models.CharField(
        max_length=100,
        blank=True,
        help_text="Browser family: Chrome, Firefox, Safari, Unknown, etc.",
    )
    os_family = models.CharField(
        max_length=100,
        blank=True,
        help_text="Operating system: Windows, macOS, iOS, Android, Linux, etc.",
    )
    device_type = models.CharField(
        max_length=50,
        blank=True,
        help_text="Device category: desktop, mobile, tablet, bot, etc.",
    )

    # ── Geolocation ────────────────────────────────────────────────────
    country = models.CharField(max_length=100, blank=True, db_index=True,
        help_text="Country name derived from IP (via MaxMind / ipapi).")
    country_code = models.CharField(max_length=3, blank=True,
        help_text="ISO 3166-1 alpha-2 country code (e.g. 'NG', 'US').")
    region = models.CharField(max_length=100, blank=True,
        help_text="State / region / province (e.g. 'Lagos', 'California').")
    city = models.CharField(max_length=100, blank=True,
        help_text="City name (e.g. 'Lagos', 'San Francisco').")
    latitude = models.DecimalField(max_digits=9, decimal_places=6,
        null=True, blank=True, help_text="Approx. latitude from IP geo-lookup.")
    longitude = models.DecimalField(max_digits=9, decimal_places=6,
        null=True, blank=True, help_text="Approx. longitude from IP geo-lookup.")

    # ── Auth context ──────────────────────────────────────────────────
    auth_method = models.CharField(
        max_length=20, choices=METHOD_CHOICES, default=METHOD_EMAIL,
        help_text="Authentication method used for this attempt.",
    )
    outcome = models.CharField(
        max_length=20, choices=OUTCOME_CHOICES, default=OUTCOME_FAILED,
        db_index=True, help_text="Result of the login attempt.",
    )
    failure_reason = models.CharField(
        max_length=100, blank=True,
        help_text=(
            "Short machine-readable failure code: "
            "'invalid_credentials', 'account_inactive', 'account_deleted', "
            "'rate_limited', 'mfa_required', etc."
        ),
    )
    is_successful = models.BooleanField(
        default=False, db_index=True,
        help_text="True iff the login attempt succeeded and tokens were issued.",
    )

    # ── Risk & Anomaly ────────────────────────────────────────────────
    risk_score = models.SmallIntegerField(default=0,
        help_text="Risk score 0-100. ≥70 triggers a security alert.")
    is_new_device = models.BooleanField(default=False,
        help_text="True if this is the first time this device fingerprint was seen.")
    is_new_country = models.BooleanField(default=False,
        help_text="True if the login country is new for this user.")
    is_tor_exit_node = models.BooleanField(default=False,
        help_text="True if the IP is a known Tor exit node.")

    # ── Session link ──────────────────────────────────────────────────
    session = models.ForeignKey(
        'authentication.UserSession',
        on_delete=models.SET_NULL,
        null=True, blank=True,
        related_name='login_events',
        help_text="The session created by this successful login (if any).",
    )

    class Meta:
        verbose_name        = "Login Event"
        verbose_name_plural = "Login Events"
        ordering            = ["-created_at"]
        indexes = [
            models.Index(fields=['user', '-created_at'],      name='le_user_ts_idx'),
            models.Index(fields=['ip_address', '-created_at'], name='le_ip_ts_idx'),
            models.Index(fields=['outcome', '-created_at'],   name='le_outcome_ts_idx'),
            models.Index(fields=['country', '-created_at'],   name='le_country_ts_idx'),
            models.Index(fields=['is_successful'],             name='le_success_idx'),
        ]

    def __str__(self):
        identifier = (
            str(self.user.email or self.user.phone)
            if self.user else 'anon'
        )
        return (
            f"[{self.outcome.upper()}] {identifier} "
            f"from {self.ip_address} ({self.country or '?'}) "
            f"at {self.created_at:%Y-%m-%d %H:%M:%S UTC}"
        )

    @classmethod
    def record(
        cls,
        *,
        user=None,
        ip_address: str,
        user_agent: str = '',
        auth_method: str = 'email',
        outcome: str = 'failed',
        failure_reason: str = '',
        is_successful: bool = False,
        session=None,
    ) -> 'LoginEvent':
        """
        Factory class-method for creating a LoginEvent in a single call.

        Designed to be called from LoginView immediately after the
        authentication decision is made. Geo-lookup and device parsing
        are deferred to a Celery task (``enrich_login_event``) that
        runs after the HTTP response is sent.
        """
        return cls.objects.create(
            user=user,
            ip_address=ip_address,
            user_agent=user_agent,
            auth_method=auth_method,
            outcome=outcome,
            failure_reason=failure_reason,
            is_successful=is_successful,
            session=session,
        )
