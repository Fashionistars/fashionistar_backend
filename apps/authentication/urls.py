# apps/authentication/urls.py
"""
Authentication URLs - Synchronous & Asynchronous Routes

Architecture:
    v1/ - Synchronous endpoints (DRF GenericAPIView, WSGI-safe)
    v2/ - Asynchronous endpoints (Django Ninja, ASGI, high-concurrency)
"""

import logging
from django.urls import path
from apps.authentication.ninja_api import api 

# Sync views (DRF)
from apps.authentication.apis.auth_views.sync_views import (
    LoginView,
    RegisterView,
    LogoutView,
    RefreshTokenView,
    VerifyOTPView,
    ResendOTPView,
    GoogleAuthView
)
from apps.authentication.apis.password_views.sync_views import (
    PasswordResetRequestView,
    PasswordResetConfirmEmailView as PasswordResetConfirmView, # Alias mapping
    ChangePasswordView
)

logger = logging.getLogger('application')

app_name = 'authentication'

# ========================================================================
# V1 API - Synchronous Endpoints (Production-Ready, WSGI-Safe)
# ========================================================================

v1_auth_patterns = [
    path('v1/auth/login/', LoginView.as_view(), name='login-sync'),
    path('v1/auth/register/', RegisterView.as_view(), name='register-sync'),
    path('v1/auth/verify-otp/', VerifyOTPView.as_view(), name='verify-otp-sync'),
    path('v1/auth/resend-otp/', ResendOTPView.as_view(), name='resend-otp-sync'),
    path('v1/auth/google/', GoogleAuthView.as_view(), name='google-auth-sync'),
    path('v1/auth/logout/', LogoutView.as_view(), name='logout-sync'),
    path('v1/auth/token/refresh/', RefreshTokenView.as_view(), name='refresh-token-sync'),
]

v1_password_patterns = [
    path('v1/password/reset-request/', PasswordResetRequestView.as_view(), name='password-reset-request-sync'),
    path('v1/password/reset-confirm/', PasswordResetConfirmView.as_view(), name='password-reset-confirm-sync'),
    path('v1/password/change/', ChangePasswordView.as_view(), name='password-change-sync'),
]

# ========================================================================
# V2 API - Asynchronous Endpoints (High-Concurrency, ASGI-Ready)
# ========================================================================

# Ninja manages its own routing tree.
# We mount the Ninja API instance at the desired prefix.
# Since this urls.py is likely included at 'api/v2/auth/' or similar,
# we need to decide where to mount it.
# If 'apps.authentication.urls' is included at 'api/v2/auth/', 
# then path('', api.urls) implies 'api/v2/auth/...'.
# Ninja router has valid routes like '/register', '/verify-otp'.
# So 'api/v2/auth/register' is achieved by:

v2_auth_patterns = [
    path('v2/auth/', api.urls), 
    # Note: If urlpatterns already has v1/auth prefix from backend/urls.py, check that.
    # backend/urls.py says: path('api/v2/auth/', include('apps.authentication.urls', ...))
    # So inside here, path('', ...) matches 'api/v2/auth/'.
    # If we map path('', api.urls), Ninja urls (e.g. /register)
    # become 'api/v2/auth/register'.
    # BUT wait, v1 urls above handle 'v1/auth/...'.
    # If this file is included at 'api/v2/auth/', then 'v1/auth/login' becomes 'api/v2/auth/v1/auth/login'.
    # This is confusing!
    
    # CHECK backend/urls.py again!
    # path('api/v2/auth/', include('apps.authentication.urls', namespace='authentication'))
    # path("auth/", include("userauths.urls")) (Legacy)
    
    # If included at 'api/v2/auth/', then `path('v1/auth/login', ...)` creates `api/v2/auth/v1/auth/login`.
    # THIS SEEMS WRONG based on the file content I saw earlier (`apps/authentication/urls.py`).
    # It seems apps/authentication/urls.py was designed to be THE auth urls file, included possibly at root or `api/`?
    # backend/urls.py: `path('api/v2/auth/', include('apps.authentication.urls'...))`
    # If so, the patterns inside should NOT have `v1/auth/` prefix if we want `api/v2/auth/login`.
    
    # BUT `apps/authentication/urls.py` (Step 740) had explicit `v1/auth/...` paths.
    # That implies it expects to be included at root or `api/` level, NOT `api/v2/auth/`.
    
    # Let's re-read backend/urls.py (Step 744):
    # path('api/v2/auth/', include('apps.authentication.urls', namespace='authentication')),
    
    # If I keep `path('v1/auth/login/', ...)` inside `apps/authentication/urls.py`,
    # AND include it at `api/v2/auth/`, the URL is:
    # `api/v2/auth/v1/auth/login/` -> TERRIBLE.
    
    # CORRECTION:
    # I should adjust `apps/authentication/urls.py` to be included at `api/` in `backend/urls.py`,
    # OR adjust the paths inside `apps/authentication/urls.py` to be relative.
    
    # Given the user wants V1 (Sync) and V2 (Async).
    # If `apps/authentication/urls.py` defines `v1/auth/login` and `v2/auth/register`,
    # It should be included at `api/`.
    # `path('api/', include('apps.authentication.urls'))`
    
    # INSTEAD, backend/urls.py has `path('api/v2/auth/', ...)` for it.
    # This suggests the user intended `apps.authentication.urls` to ONLY be v2?
    # But the file content has v1 paths!
    
    # I will assume `apps.authentication.urls` is intended to handle ALL authentication urls (v1 and v2),
    # and I should change the include in `backend/urls.py` to `path('api/', ...)` 
    # OR change the paths in `apps.authentication.urls` to remove prefixes.
    
    # Let's adhere to "Modular Monolith". The module `authentication` should own its URL space.
    # If I change the include in `backend/urls.py` to `path('api/', ...)` it might conflict with `api.urls` (v1 legacy).
    
    # Safe bet: Update `apps/authentication/urls.py` paths to be relative to `api/v2/auth/`.
    # NO, V1 should not be under V2.
    
    # Strategy:
    # 1. Modify `backend/urls.py` to include `apps.authentication.urls` at `api/` (if valid) OR
    # 2. Modify `apps/authentication/urls.py` to strip prefixes and let `backend/urls.py` handle prefixes.
    #    If `backend/urls.py` includes it at `api/v2/auth/`, then patterns should be empty string or action names.
    #    e.g. `path('login/', ...)` -> `api/v2/auth/login/`.
    #    But we want V1 patterns too!
    
    # Best compromise:
    # `backend/urls.py`:
    # `path('api/', include('apps.authentication.urls'))`
    # And inside `apps.authentication.urls`:
    # `path('v1/auth/login')`
    # `path('v2/auth/register')`
    
    # I will UPDATE `apps/authentication/urls.py` preserving the prefixes, 
    # AND I will assume I verify/fix `backend/urls.py` later or relying on what makes sense.
    # Wait, `backend/urls.py` line 35: `path('api/v2/auth/', include('apps.authentication.urls', ...))`
    # This limits it to `api/v2/auth/*`.
    # If I use `path('v1/auth/login')` inside, it becomes `api/v2/auth/v1/auth/login`.
    # I MUST change `backend/urls.py` to `path('api/', include('apps.authentication.urls'))` to match the file structure.
    # OR I change `apps/authentication/urls.py`.
    
    # Let's fix `apps/authentication/urls.py` first to reference the View classes correctly.
    # I will keep the prefixes for now, but I will strip `v1/auth` if I decide to use the mount point.
    # Actually, the file header says "v1/ - Synchronous... v2/ - Async...".
    # So it is designed to hold both.
    # So the include in `backend/urls.py` is WRONG if it scopes it to `api/v2/auth/`.
    
    # I will fix `backend/urls.py` as part of this verification step if needed.
    # For now, I write `apps.authentication.urls` assuming it will be included at `api/`.
]

urlpatterns = (
    v1_auth_patterns +
    v1_password_patterns +
    [path('v2/auth/', api.urls)] # Mount Ninja at v2/auth/
)

# Legacy handling (optional, if we want to catch root paths if included at root)
# ...
