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

    def get(self, request: Request, user_id: str, *args, **kwargs) -> Response:
        try:
            user = UnifiedUser.objects.all_with_deleted().get(pk=user_id)
        except UnifiedUser.DoesNotExist:
            return Response({"detail": "User not found."}, status=404)

        return Response({
            "id": str(user.pk),
            "email": user.email,
            "phone": str(user.phone) if user.phone else None,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "member_id": user.member_id,
            "role": user.role,
            "auth_provider": user.auth_provider,
            "is_active": user.is_active,
            "is_verified": user.is_verified,
            "is_deleted": user.is_deleted,
            "is_superuser": user.is_superuser,
            "is_staff": user.is_staff,
            "bio": user.bio,
            "country": user.country,
            "state": user.state,
            "city": user.city,
            "address": user.address,
            "avatar": user.avatar.url if user.avatar else None,
            "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            "updated_at": user.updated_at.isoformat() if user.updated_at else None,
            "deleted_at": getattr(user, "deleted_at", None).isoformat() if getattr(user, "deleted_at", None) else None,
        })

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

        return Response({
            "success": True,
            "message": "User account updated successfully.",
            "data": {"user_id": str(user.pk)},
        })



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
