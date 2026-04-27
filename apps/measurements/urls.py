# apps/measurements/urls.py
from django.urls import path
from apps.measurements.apis.sync import (
    MeasurementProfileListCreateView,
    MeasurementProfileDetailView,
    SetDefaultProfileView,
)

app_name = "measurements"

urlpatterns = [
    path("", MeasurementProfileListCreateView.as_view(), name="profile-list-create"),
    path("<int:profile_id>/", MeasurementProfileDetailView.as_view(), name="profile-detail"),
    path("<int:profile_id>/set-default/", SetDefaultProfileView.as_view(), name="profile-set-default"),
]
