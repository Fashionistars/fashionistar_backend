"""
Compatibility shim — forwards to apps.providers.MirrorSize.

The canonical implementation now lives in apps/providers/MirrorSize/.
This shim keeps existing measurement service imports working without
any other code changes required.

Do NOT add new code here. Import from apps.providers.MirrorSize instead.
"""
from apps.providers.MirrorSize.mirrorsize_provider import (  # noqa: F401
    MirrorSizeClient,
    MirrorSizeProviderError,
)

__all__ = ["MirrorSizeClient", "MirrorSizeProviderError"]
