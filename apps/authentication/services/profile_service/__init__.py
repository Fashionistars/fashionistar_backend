# apps/authentication/services/profile_service/__init__.py
from .sync_service import SyncAuthService  # noqa: F401

__all__ = ["SyncProfileService"]
