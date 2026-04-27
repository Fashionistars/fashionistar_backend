# apps/notification/apis/sync/notification_views.py
"""
DRF synchronous views for the Notification domain.

Endpoints:
  GET    /api/v1/notifications/              — List user's in-app feed
  GET    /api/v1/notifications/<id>/         — Detail + mark as read
  POST   /api/v1/notifications/mark-all-read/ — Mark all read
  GET    /api/v1/notifications/unread-count/  — Return unread badge count
  GET    /api/v1/notifications/preferences/  — Get preferences
  POST   /api/v1/notifications/preferences/  — Set a preference
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.renderers import CustomJSONRenderer, success_response, error_response
from apps.common.permissions import IsAuthenticatedAndActive
from apps.notification.models import NotificationPreference
from apps.notification.selectors import (
    get_user_notifications,
    get_unread_count,
    get_notification_by_id,
)
from apps.notification.serializers import (
    NotificationSerializer,
    NotificationPreferenceSerializer,
    NotificationPreferenceWriteSerializer,
)
from apps.notification.services import mark_as_read, mark_all_as_read

logger = logging.getLogger(__name__)

_RENDERERS = [CustomJSONRenderer, BrowsableAPIRenderer]


class NotificationListView(APIView):
    """
    GET /api/v1/notifications/
    Returns the authenticated user's in-app notification feed.
    Supports ?unread_only=true to filter unread.
    """
    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def get(self, request):
        unread_only = request.query_params.get("unread_only", "").lower() == "true"
        qs = get_user_notifications(
            user_id=request.user.id,
            unread_only=unread_only,
            limit=50,
        )
        serializer = NotificationSerializer(qs, many=True)
        return success_response(data=serializer.data)


class NotificationDetailView(APIView):
    """
    GET /api/v1/notifications/<id>/
    Returns a single notification and marks it as read.
    """
    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def get(self, request, notification_id):
        notif = get_notification_by_id(
            notification_id=notification_id,
            user_id=request.user.id,
        )
        if not notif:
            return error_response(
                message="Notification not found.",
                status=status.HTTP_404_NOT_FOUND,
            )
        # Mark as read on retrieval
        mark_as_read(user=request.user, notification_id=notification_id)
        notif.refresh_from_db()
        return success_response(data=NotificationSerializer(notif).data)


class MarkAllReadView(APIView):
    """POST /api/v1/notifications/mark-all-read/"""
    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request):
        count = mark_all_as_read(user=request.user)
        return success_response(
            data={"marked_read": count},
            message=f"{count} notification(s) marked as read.",
        )


class UnreadCountView(APIView):
    """GET /api/v1/notifications/unread-count/"""
    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def get(self, request):
        count = get_unread_count(user_id=request.user.id)
        return success_response(data={"unread_count": count})


class NotificationPreferenceView(APIView):
    """
    GET  /api/v1/notifications/preferences/ — List current preferences
    POST /api/v1/notifications/preferences/ — Set/update a preference
    """
    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def get(self, request):
        prefs = NotificationPreference.objects.filter(user=request.user)
        return success_response(
            data=NotificationPreferenceSerializer(prefs, many=True).data
        )

    def post(self, request):
        serializer = NotificationPreferenceWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        pref, created = NotificationPreference.objects.update_or_create(
            user=request.user,
            notification_type=serializer.validated_data["notification_type"],
            channel=serializer.validated_data["channel"],
            defaults={"enabled": serializer.validated_data["enabled"]},
        )
        return success_response(
            data=NotificationPreferenceSerializer(pref).data,
            message="Preference saved.",
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )
