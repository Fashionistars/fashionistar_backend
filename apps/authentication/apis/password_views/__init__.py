from .sync_views import PasswordResetRequestView as SyncPasswordResetRequestView
from .async_views import (
    PasswordResetRequestView,
    PasswordResetConfirmEmailView,
    PasswordResetConfirmPhoneView,
    ChangePasswordView
)

__all__ = [
    'PasswordResetRequestView', 
    'PasswordResetConfirmEmailView', 
    'PasswordResetConfirmPhoneView', 
    'ChangePasswordView'
]
