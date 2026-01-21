from .sync_views import RegisterView as SyncRegisterView, LoginView as SyncLoginView
from .async_views import RegisterView, LoginView, GoogleAuthView, VerifyOTPView, ResendOTPView, LogoutView

# Default export is Async for new apps, but can import Sync versions explicitly if needed.
# For URLs, we use Async.
__all__ = ['RegisterView', 'LoginView', 'GoogleAuthView', 'VerifyOTPView', 'ResendOTPView', 'LogoutView']
