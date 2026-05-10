# apps/providers/__init__.py
"""
Fashionistar Provider Registry — Top-level package.

This package is the single authoritative registry for every third-party
integration driver used by the Fashionistar platform.  Providers are
organised into named sub-packages by domain:

Sub-Packages:
    Payment/    — Paystack, Flutterwave, OlivePay payment gateway drivers.
    KYC/        — Smile Identity, Dojah, Youverify identity verification drivers.
    SMS/        — Termii, Twilio, BulkSMS Nigeria SMS dispatch drivers.
    SMTP/       — Brevo, Mailgun, Zoho Mail transactional email drivers.
    Cloudinary/ — Cloudinary media upload & transformation driver.
    MirrorSize/ — MirrorSize body measurement API driver.
    backends/   — Django email backend + SMS dispatch backend wired to the
                  admin-selected active provider.
    models/     — ProviderConfig DB models for each provider domain.

Architecture:
    All drivers share:
      - ``apps.common.http.ProviderSyncHTTPClient`` /
        ``apps.common.http.ProviderAsyncHTTPClient`` for structured HTTP calls
        with automatic retry, structured logging, and idempotency headers.
      - ``apps.providers.circuit_breaker.CircuitBreaker`` to isolate cascading
        failures when a third-party gateway is degraded.
      - Admin-managed ``ProviderConfig`` DB models so credentials and active
        provider selection are changeable from the Django Admin without redeployment.

Usage::

    # Payment (direct client call)
    from apps.providers.Payment.paystack import PaystackClient
    data = PaystackClient.initialize_payment(email=..., amount=..., reference=...)

    # KYC (via service layer — preferred)
    from apps.kyc.services.kyc_service import KycService
    result = await KycService.verify_bvn(user=user, bvn_hash=..., last4=...)
"""
