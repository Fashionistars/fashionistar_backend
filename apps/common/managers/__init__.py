# apps/common/managers/__init__.py
"""
Centralized manager exports for ``apps.common``.

Provides soft-delete, email, and SMS managers for import
throughout the application:

    from apps.common.managers import SoftDeleteManager
    from apps.common.managers import EmailManager
    from apps.common.managers import SMSManager
"""

from apps.common.managers.soft_delete import (    # noqa: F401
    SoftDeleteManager,
    SoftDeleteQuerySet,
)
from apps.common.managers.email import (          # noqa: F401
    EmailManager,
    EmailManagerError,
)
from apps.common.managers.sms import (            # noqa: F401
    SMSManager,
    SMSManagerError,
)
