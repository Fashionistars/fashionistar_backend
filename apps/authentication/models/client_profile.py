# apps/authentication/models/client_profile.py
"""
Compatibility import for the Phase 2 ClientProfile move.

The canonical ``ClientProfile`` now lives in ``apps.client.models`` so all
client-domain concerns stay in the client bounded context. This shim preserves
older imports such as ``from apps.authentication.models import ClientProfile``
without defining a second model class.
"""

from apps.client.models.client_profile import ClientProfile

__all__ = ["ClientProfile"]
