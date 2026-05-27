# apps/global_platform_settings/admin_backend/urls.py
from django.urls import path
from .views import AdminPlatformSettingsUpdateView

app_name = "admin_global_platform_settings"

urlpatterns = [
    path("update/", AdminPlatformSettingsUpdateView.as_view(), name="admin-settings-update"),
]

