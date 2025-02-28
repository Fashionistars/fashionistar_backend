from django.urls import path
from userauths.views import (
    RegisterViewCelery,
    VerifyOTPView,
    ResendOTPView,
    PasswordResetRequestView,
    PasswordResetConfirmEmailView,
    PasswordResetConfirmPhoneView,
    LoginView,
    LogoutView,
    ProfileView,
    USERSPROFILELISTVIEW
)





urlpatterns = [
    path('register/', RegisterViewCelery.as_view(), name='registration'),
    path('login/', LoginView.as_view(), name='login'),
    path('logout/', LogoutView.as_view(), name="logout"),
    path('verify-otp/', VerifyOTPView.as_view(), name='verify-otp'),
    path('resend-otp/', ResendOTPView.as_view(), name='resend-otp'),
    path('password-reset-request/', PasswordResetRequestView.as_view(), name='password-reset-request'),
    path('password-reset-confirm-email/<str:uidb64>/<str:token>/', PasswordResetConfirmEmailView.as_view(), name='password-reset-confirm-email'),
    path('password-reset-confirm-phone/', PasswordResetConfirmPhoneView.as_view(), name='password-reset-confirm-phone'),
    path('users/profile/', USERSPROFILELISTVIEW.as_view(), name='ALL-USERS-AND-PROFILE'),
    path('user/profile/', ProfileView.as_view(), name='user_profile'),  # Removed pid
]
















# from rest_framework_simplejwt.views import TokenRefreshView
# path('token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
# path('token/', MyTokenObtainPairView.as_view(), name='token_obtain_pair'),

