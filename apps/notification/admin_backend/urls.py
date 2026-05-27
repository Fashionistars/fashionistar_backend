# apps/notification/admin_backend/urls.py
from django.urls import path
from .views import AdminBroadcastNotificationView

urlpatterns = [
    path("broadcast/", AdminBroadcastNotificationView.as_view(), name="admin-notification-broadcast"),
]
