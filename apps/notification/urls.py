# apps/notification/urls.py
from django.urls import path
from apps.notification.apis.sync import (
    NotificationListView,
    NotificationDetailView,
    MarkAllReadView,
    UnreadCountView,
    NotificationPreferenceView,
)

app_name = "notification"

urlpatterns = [
    # Feed
    path("", NotificationListView.as_view(), name="notification-list"),
    path("<int:notification_id>/", NotificationDetailView.as_view(), name="notification-detail"),
    # Actions
    path("mark-all-read/", MarkAllReadView.as_view(), name="notification-mark-all-read"),
    path("unread-count/", UnreadCountView.as_view(), name="notification-unread-count"),
    # Preferences
    path("preferences/", NotificationPreferenceView.as_view(), name="notification-preferences"),
]
