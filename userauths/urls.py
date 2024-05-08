from django.urls import include, path
from rest_framework import routers
from rest_framework_simplejwt.views import TokenObtainPairView,TokenRefreshView,TokenBlacklistView

from .views import *


urlpatterns = [
    path("sign-up", RegisterView.as_view(), name='register'),
    path('otp-verification', VerifyUserViewSet.as_view({'post': 'verify_email'}), name="otp-verification")
]