# apps/providers/admin_backend/urls.py
from django.urls import path
from .views import (
    AdminEmailConfigUpdateView,
    AdminSMSConfigUpdateView,
    AdminKYCConfigUpdateView,
    AdminCloudinaryConfigUpdateView,

)

app_name = "admin_providers"

urlpatterns = [
    path("email/update/", AdminEmailConfigUpdateView.as_view(), name="admin-providers-email-update"),
    path("sms/update/", AdminSMSConfigUpdateView.as_view(), name="admin-providers-sms-update"),
    path("kyc/update/", AdminKYCConfigUpdateView.as_view(), name="admin-providers-kyc-update"),
    path("cloudinary/update/", AdminCloudinaryConfigUpdateView.as_view(), name="admin-providers-cloudinary-update"),

]
