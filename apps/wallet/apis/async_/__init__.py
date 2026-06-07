# apps/wallet/apis/async_/__init__.py
"""
Wallet Domain — Django-Ninja Async API Sub-Package.

Exports all async routers for registration in the central Ninja API router.

Mounted at: /api/v1/ninja/wallet/

Routers:
    wallet_async_router  — READ-ONLY dashboard and balance endpoints.
                           (GET /dashboard/, GET /balance/)

    mutation_router      — HIGH-SECURITY write endpoints.
                           (POST /company/payout/)

Security Architecture:
    - Read router (wallet_async_router): authenticated users only.
    - Mutation router (mutation_router): Double-Door secured company payout.
      Restricted to the Primary Company Superuser:
      ``fashionistarclothings@outlook.com``.

Registration (in central Ninja config)::

    from apps.wallet.apis.async_ import wallet_async_router, mutation_router

    api.add_router("/wallet/", wallet_async_router)
    api.add_router("/wallet/", mutation_router)

Note:
    The wallet is provisioned automatically on user creation via
    ``WalletProvisioningService``; there is no ``POST /wallet/create/`` endpoint.

    Standard client/vendor withdrawal requests are handled on the DRF sync
    surface at ``/api/v1/wallet/withdrawal/``.
"""

from apps.wallet.apis.async_.wallet_views import router as wallet_async_router
from apps.wallet.apis.async_.mutation_views import router as mutation_router

__all__ = [
    "wallet_async_router",
    "mutation_router",
]
