# apps/authentication/apis/biometric_views/__init__.py
"""
Biometric Views Package — Sync (DRF) only.

Async biometric views deprecated (Phase 7). Re-introduce when WebAuthn
async support is specifically needed.
"""
from .sync_views import BiometricRegisterOptionsView as SyncBiometricRegisterOptionsView  # noqa: F401

__all__ = [
    'SyncBiometricRegisterOptionsView',
]
