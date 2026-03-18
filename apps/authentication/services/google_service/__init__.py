# apps/authentication/services/google_service/__init__.py
# Async service deprecated (Phase 7). Re-enable for async contexts in future phases.
from .sync_service import SyncGoogleAuthService  # noqa: F401

__all__ = ['SyncGoogleAuthService']
