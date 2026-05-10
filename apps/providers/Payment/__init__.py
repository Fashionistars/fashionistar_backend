# apps/providers/Payment/__init__.py
"""
Payment Provider Sub-Package.

Exposes three drop-in payment gateway drivers, each implementing an identical
public API surface so the payment service layer can swap gateways via config:

Drivers:
    PaystackClient    — Paystack Africa (primary gateway, widest card + bank support).
    FlutterwaveClient — Flutterwave (cross-Africa, multi-currency, mobile money).
    OlivePayClient    — OlivePay (local Nigerian fintech, USSD + QR payments).

All drivers share:
    - ``ProviderSyncHTTPClient`` for synchronous DRF view calls.
    - ``ProviderAsyncHTTPClient`` for async Django-Ninja view calls.
    - ``CircuitBreaker`` to isolate failures when a gateway is degraded.
    - HMAC-SHA256 webhook signature verification.

Amounts:
    Paystack and OlivePay receive amounts in **kobo** (NGN × 100, integer).
    Flutterwave receives amounts in full **naira** units (Decimal string, no conversion).

Environment Variables Required:
    Paystack:
        PAYSTACK_SECRET_KEY, PAYSTACK_PUBLIC_KEY
    Flutterwave:
        FLUTTERWAVE_SECRET_KEY, FLUTTERWAVE_PUBLIC_KEY, FLUTTERWAVE_WEBHOOK_SECRET_HASH
    OlivePay:
        OLIVEPAY_API_KEY, OLIVEPAY_SECRET_KEY, OLIVEPAY_BASE_URL (optional)
"""

from apps.providers.Payment.flutterwave import FlutterwaveClient
from apps.providers.Payment.olivepay import OlivePayClient
from apps.providers.Payment.paystack import PaystackClient

__all__ = [
    "PaystackClient",
    "FlutterwaveClient",
    "OlivePayClient",
]
