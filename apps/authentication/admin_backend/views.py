# apps/authentication/admin_backend/views.py
"""
DRF sync mutation views for the authentication admin domain.

These views intentionally stay thin:
  - permission gating lives in apps.admin_backend.permissions
  - validation lives in serializers.py
  - business mutations live in services.py
"""

from __future__ import annotations

import logging

from django.contrib.auth import get_user_model
from django.db import transaction
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.admin_backend.permissions import IsAdminUser, IsSuperuserOnly
from apps.common.events import event_bus
from apps.common.renderers import CustomJSONRenderer, success_response

from .serializers import (
    AdminUserForcePasswordSerializer,
    AdminUserRoleUpdateSerializer,
    AdminUserSuspendSerializer,
    AdminUserUpdateSerializer,
)
from .services import AdminUserService

UnifiedUser = get_user_model()
logger = logging.getLogger(__name__)


class AdminUserSuspendView(APIView):
    permission_classes = [IsAdminUser]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request: Request, user_id: str, *args, **kwargs) -> Response:
        serializer = AdminUserSuspendSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = AdminUserService.suspend_user(
            user_id=user_id,
            reason=serializer.validated_data["reason"],
            admin_user=request.user,
        )
        return success_response(
            data={"user_id": str(user.pk), "is_active": user.is_active},
            message="User account has been successfully suspended.",
        )


class AdminUserReactivateView(APIView):
    permission_classes = [IsAdminUser]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request: Request, user_id: str, *args, **kwargs) -> Response:
        user = AdminUserService.reactivate_user(
            user_id=user_id,
            admin_user=request.user,
        )
        return success_response(
            data={"user_id": str(user.pk), "is_active": user.is_active},
            message="User account has been successfully reactivated.",
        )


class AdminUserUpdateView(APIView):
    permission_classes = [IsAdminUser]
    renderer_classes = [CustomJSONRenderer]

    @transaction.atomic
    def put(self, request: Request, user_id: str, *args, **kwargs) -> Response:
        user = UnifiedUser.objects.all_with_deleted().get(pk=user_id)
        serializer = AdminUserUpdateSerializer(instance=user, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        serializer.save()

        updated_fields = list(serializer.validated_data.keys())
        logger.info(
            "Admin %s updated user %s fields: %s",
            request.user.pk,
            user.pk,
            updated_fields,
        )
        event_bus.emit_on_commit(
            "user.updated_by_admin",
            user_id=str(user.pk),
            admin_user_id=str(request.user.pk),
            fields=updated_fields,
        )

        return success_response(
            data={"user_id": str(user.pk)},
            message="User account updated successfully.",
        )


class AdminUserVerifyView(APIView):
    permission_classes = [IsAdminUser]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request: Request, user_id: str, *args, **kwargs) -> Response:
        user = AdminUserService.admin_verify_user(
            user_id=user_id,
            admin_user=request.user,
        )
        return success_response(
            data={"user_id": str(user.pk), "is_verified": user.is_verified},
            message="User verification status updated to verified.",
        )


class AdminUserForcePasswordResetView(APIView):
    permission_classes = [IsSuperuserOnly]
    renderer_classes = [CustomJSONRenderer]

    @transaction.atomic
    def post(self, request: Request, user_id: str, *args, **kwargs) -> Response:
        # Backward compatible behavior: if no password body is sent, emit the
        # admin-triggered reset event without directly rotating credentials.
        if not request.data:
            user = UnifiedUser.objects.all_with_deleted().get(pk=user_id)
            event_bus.emit_on_commit(
                "user.force_password_reset",
                user_id=str(user.pk),
                admin_user_id=str(request.user.pk),
            )
            logger.warning(
                "Superuser %s triggered a password reset flow for user %s",
                request.user.pk,
                user.pk,
            )
            return success_response(
                data={"user_id": str(user.pk)},
                message="Password reset process successfully triggered for user.",
            )

        serializer = AdminUserForcePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        user = AdminUserService.admin_force_reset_password(
            user_id=user_id,
            new_password=serializer.validated_data["new_password"],
            admin_user=request.user,
        )
        return success_response(
            data={"user_id": str(user.pk)},
            message="User password was reset successfully.",
        )


class AdminUserRoleUpdateView(APIView):
    permission_classes = [IsSuperuserOnly]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request: Request, user_id: str, *args, **kwargs) -> Response:
        payload = request.data.copy()
        if "role" in payload and "new_role" not in payload:
            payload["new_role"] = payload["role"]

        serializer = AdminUserRoleUpdateSerializer(data=payload)
        serializer.is_valid(raise_exception=True)

        user = AdminUserService.admin_update_user_role(
            user_id=user_id,
            new_role=serializer.validated_data["new_role"],
            admin_user=request.user,
        )
        return success_response(
            data={"user_id": str(user.pk), "role": user.role},
            message="User role updated successfully.",
        )
