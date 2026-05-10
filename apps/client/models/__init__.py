# apps/client/models/__init__.py
"""
apps.client.models public API.

Import everything from here so other apps never need to know
the internal file structure:

    from apps.client.models import ClientProfile, ClientAddress
"""
from apps.client.models.client_profile import ClientProfile
from apps.client.models.client_address import ClientAddress

__all__ = [
    "ClientProfile",
    "ClientAddress",
]
