# apps/global_platform_settings/__init__.py
"""
GlobalPlatformSettings — Standalone Django application.

This app owns the ``PlatformSettings`` singleton model which centralises every
admin-configurable business constant for the Fashionistar platform:

  - Vendor commission rates & client platform fees
  - Measurement fees
  - Wallet top-up / withdrawal limits
  - Cash-on-Delivery and in-store payment configuration
  - KYC retry / lockout policy
  - NGN → USD fallback exchange rate
  - Platform identity (name, support contacts, legal URLs)

Quick Usage::

    from apps.global_platform_settings.cache import get_platform_settings

    cfg = get_platform_settings()
    rate = cfg.vendor_commission_rate   # Decimal e.g. Decimal("0.10")
    fee  = cfg.measurement_fee_ngn      # Decimal e.g. Decimal("1000.00")

The singleton is Redis-cached with a 60-second TTL so admin changes propagate
to all running processes within one minute, without requiring redeployment.
"""
