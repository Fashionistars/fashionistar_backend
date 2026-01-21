from .sync_views import BiometricRegisterOptionsView as SyncBiometricRegisterOptionsView
from .async_views import (
    BiometricRegisterOptionsView,
    BiometricRegisterVerifyView,
    BiometricLoginOptionsView,
    BiometricLoginVerifyView
)

__all__ = [
    'BiometricRegisterOptionsView',
    'BiometricRegisterVerifyView',
    'BiometricLoginOptionsView',
    'BiometricLoginVerifyView'
]
