# apps/providers/models/base.py
"""
AbstractProviderConfig — Singleton base model for all admin-switchable provider configs.

Design contract (identical for Email, SMS, KYC):
  - Only ONE row may exist per concrete model (singleton enforcement via clean/delete).
  - Admin cannot delete the row; they must edit it to switch providers.
  - On every save(), the provider cache is busted so the next request picks up the change.
  - health_status / last_health_check track the last connectivity probe result.

Security note:
  - Raw credentials are NEVER stored in plain text.
  - Concrete models must use EncryptedCharField (django-cryptography) for secrets.
  - Only the provider class path and non-sensitive metadata are stored as cleartext.
"""

from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.common.models import TimeStampedModel


class HealthStatus(models.TextChoices):
    UNKNOWN = "unknown", _("Unknown")
    HEALTHY = "healthy", _("Healthy ✅")
    DEGRADED = "degraded", _("Degraded ⚠️")
    UNHEALTHY = "unhealthy", _("Unhealthy ❌")


class CircuitState(models.TextChoices):
    CLOSED = "closed", _("Closed (Normal)")
    OPEN = "open", _("Open (Provider Failing — Switch Required)")
    HALF_OPEN = "half_open", _("Half-Open (Probing)")


class AbstractProviderConfig(TimeStampedModel):
    """
    Singleton base for all provider configuration models.

    Subclasses add:
      - provider_class_path (CharField) — the Python import path to the concrete driver.
      - Any encrypted credential fields (api_key, api_secret, webhook_secret…).
      - provider-specific help text and choices.

    Cache contract:
      - Every concrete subclass is assigned a deterministic cache key:
        ``provider_cfg:<app_label>:<model_name>``
      - The post_save signal in apps.providers.signals calls invalidate_provider_cache()
        immediately after any admin save, ensuring zero-delay propagation.
    """

    # ── Health Tracking ────────────────────────────────────────────────────────
    health_status = models.CharField(
        max_length=20,
        choices=HealthStatus.choices,
        default=HealthStatus.UNKNOWN,
        verbose_name=_("Health Status"),
        help_text=_("Last recorded health check result for this provider."),
    )
    last_health_check = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Health Check"),
    )

    # ── Circuit Breaker State ──────────────────────────────────────────────────
    circuit_state = models.CharField(
        max_length=20,
        choices=CircuitState.choices,
        default=CircuitState.CLOSED,
        verbose_name=_("Circuit State"),
        help_text=_(
            "OPEN means the provider is currently failing. "
            "Switch to another provider and save to reset the circuit."
        ),
    )
    failure_count = models.PositiveSmallIntegerField(
        default=0,
        verbose_name=_("Consecutive Failure Count"),
        help_text=_("Resets to 0 when the provider call succeeds."),
    )
    last_failure_at = models.DateTimeField(
        null=True,
        blank=True,
        verbose_name=_("Last Failure Timestamp"),
    )

    # ── Timestamps and uuid ( id inherited from TimeStampedModel) ─────────────────────────────────────────────────────────────

    class Meta:
        abstract = True

    # ── Singleton Enforcement ──────────────────────────────────────────────────

    def clean(self) -> None:
        super().clean()
        if self.pk is None and self.__class__.objects.exists():
            raise ValidationError(
                _(
                    "Singleton constraint: only one %(model)s may exist. "
                    "Edit the existing configuration instead of creating a new one."
                )
                % {"model": self.__class__.__name__}
            )

    def delete(self, *args, **kwargs):  # type: ignore[override]
        raise ValidationError(
            _(
                "You cannot delete %(model)s. "
                "This configuration is required for the system to function. "
                "Edit it to switch providers instead."
            )
            % {"model": self.__class__.__name__}
        )

    def save(self, *args, **kwargs) -> None:
        self.full_clean()
        super().save(*args, **kwargs)
        # Always bust cache on every admin save
        self._invalidate_cache()

    def _invalidate_cache(self) -> None:
        try:
            from apps.providers.cache import invalidate_provider_cache

            invalidate_provider_cache(self.__class__)
        except Exception:
            pass  # Cache invalidation must never break a save

    # ── Circuit Breaker Helpers (called by circuit_breaker.py) ────────────────

    def record_failure(self) -> None:
        """Increment failure counter and possibly open the circuit."""
        self.failure_count += 1
        self.last_failure_at = timezone.now()
        # Use update() to avoid triggering save() → cache bust loop
        self.__class__.objects.filter(pk=self.pk).update(
            failure_count=self.failure_count,
            last_failure_at=self.last_failure_at,
            circuit_state=(
                CircuitState.OPEN if self.failure_count >= 3 else self.circuit_state
            ),
        )

    def record_success(self) -> None:
        """Reset failure counter and close the circuit."""
        self.__class__.objects.filter(pk=self.pk).update(
            failure_count=0,
            circuit_state=CircuitState.CLOSED,
            health_status=HealthStatus.HEALTHY,
            last_health_check=timezone.now(),
        )
