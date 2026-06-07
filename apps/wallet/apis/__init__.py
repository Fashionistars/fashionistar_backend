# apps/wallet/apis/__init__.py
"""
Wallet APIs — Top-Level Package Exports.

Re-exports all async wallet routers for direct import without needing to
know the nested package structure.

Usage in ninja_api.py:
    from apps.wallet.apis.async_.wallet_views import router as wallet_router
    from apps.wallet.apis.async_.mutation_views import router as wallet_mutation_router
"""
from apps.wallet.apis.async_.wallet_views import router as wallet_async_router
from apps.wallet.apis.async_.mutation_views import router as wallet_mutation_router

__all__ = [
    "wallet_async_router",
    "wallet_mutation_router",
]
