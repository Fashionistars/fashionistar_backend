from django.urls import path
from rest_framework_simplejwt.views import TokenRefreshView, TokenVerifyView

# Import new Modular Views
from apps.authentication.apis import (
    auth_views,
    password_views,
    profile_views,
    biometric_views
)

app_name = 'authentication'

urlpatterns = [
    # ==========================================
    # 1. CORE AUTHENTICATION (Registration & Login)
    # ==========================================
    path('register/', auth_views.RegisterView.as_view(), name='registration'),
    path('login/', auth_views.LoginView.as_view(), name='login'),
    # path('logout/', auth_views.LogoutView.as_view(), name='logout'), # Implement if LogoutView exists
    
    # Google Hybrid Auth
    path('google/', auth_views.GoogleAuthView.as_view(), name='google_auth'),

    # ==========================================
    # 2. OTP & VERIFICATION
    # ==========================================
    path('verify-otp/', auth_views.VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', auth_views.ResendOTPView.as_view(), name='resend-otp'),

    # ==========================================
    # 3. PASSWORD MANAGEMENT
    # ==========================================
    path('password-reset-request/', password_views.PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset-confirm-email/<str:uidb64>/<str:token>/', password_views.PasswordResetConfirmEmailView.as_view(), name='password-reset-confirm-email'),
    path('password-reset-confirm-phone/', password_views.PasswordResetConfirmPhoneView.as_view(), name='password-reset-confirm-phone'),
    path('change-password/', password_views.ChangePasswordView.as_view(), name='change-password'),

    # ==========================================
    # 4. USER PROFILES
    # ==========================================
    path('user/profile/', profile_views.UserProfileDetailView.as_view(), name='user_profile'),
    path('users/profile/', profile_views.UserListView.as_view(), name='all-users-and-profiles'),

    # ==========================================
    # 5. BIOMETRIC AUTH
    # ==========================================
    path('biometric/register/options/', biometric_views.BiometricRegisterOptionsView.as_view(), name='biometric-register-options'),
    path('biometric/register/verify/', biometric_views.BiometricRegisterVerifyView.as_view(), name='biometric-register-verify'),
    path('biometric/login/options/', biometric_views.BiometricLoginOptionsView.as_view(), name='biometric-login-options'),
    path('biometric/login/verify/', biometric_views.BiometricLoginVerifyView.as_view(), name='biometric-login-verify'),

    # ==========================================
    # 6. JWT TOKEN MANAGEMENT
    # ==========================================
    path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    path('token/verify/', TokenVerifyView.as_view(), name='token_verify'),
]
