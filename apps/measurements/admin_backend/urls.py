# apps/measurements/admin_backend/urls.py
from django.urls import path
from .views import AdminVerifyMeasurementView

urlpatterns = [
    path("<str:profile_id>/verify/", AdminVerifyMeasurementView.as_view(), name="admin-measurements-verify"),
]
