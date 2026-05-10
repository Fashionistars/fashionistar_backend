# apps/wallet/apis/async_/__init__.py
"""
Wallet Domain — Django-Ninja Async API Sub-Package.

Exports the async router for registration in the central Ninja API router.

Mounted at: /api/v1/ninja/wallet/

Endpoints:
    GET /dashboard/ — Full wallet snapshot (balance + escrow hold aggregates).
    GET /balance/   — Lightweight balance-only snapshot (single DB query).

Note:
    All mutation endpoints (PIN set/change, wallet top-up initiation, withdrawal)
    live on the DRF sync surface at ``/api/v1/wallet/``.  This async namespace
    is READ-ONLY by design, enforcing the Fashionistar write-sync / read-async
    architectural boundary.

    The wallet is always provisioned automatically on user creation via
    ``WalletProvisioningService``; there is no ``POST /wallet/create/`` endpoint.
"""

from apps.wallet.apis.async_.wallet_views import router as wallet_async_router

__all__ = ["wallet_async_router"]
