# apps/wallet/apis/__init__.py
from .async_.wallet_views import router as wallet_async_router

__all__ = ["wallet_async_router"]
