# apps/authentication/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.exceptions import PermissionDenied, ValidationError
from django.contrib.auth import get_user_model
from django.db import transaction
from apps.common.renderers import CustomJSONRenderer, success_response
from apps.common.events import event_bus
from apps.authentication.admin_backend.services import AdminUserService
from apps.authentication.admin_backend.serializers import BanUserSerializer

UnifiedUser = get_user_model()
logger = logging.getLogger(__name__)

class AdminUserSuspendView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request, user_id, *args, **kwargs):
        if not (request.user.is_staff or request.user.role in ["admin", "super_admin"]):
            raise PermissionDenied("You do not have permission to perform this action.")
            
        serializer = BanUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data["reason"]
        
        try:
            user = AdminUserService.ban_user(user_id=user_id, reason=reason, admin_user=request.user)
            return success_response(
                data={"user_id": str(user.pk), "is_active": user.is_active},
                message="User account has been successfully suspended."
            )
        except Exception as e:
            raise ValidationError(str(e))

class AdminUserReactivateView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    def post(self, request, user_id, *args, **kwargs):
        if not (request.user.is_staff or request.user.role in ["admin", "super_admin"]):
            raise PermissionDenied("You do not have permission to perform this action.")
            
        try:
            user = AdminUserService.unban_user(user_id=user_id, admin_user=request.user)
            return success_response(
                data={"user_id": str(user.pk), "is_active": user.is_active},
                message="User account has been successfully reactivated."
            )
        except Exception as e:
            raise ValidationError(str(e))

class AdminUserUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    @transaction.atomic
    def put(self, request, user_id, *args, **kwargs):
        if not (request.user.is_staff or request.user.role in ["admin", "super_admin"]):
            raise PermissionDenied("You do not have permission to perform this action.")
            
        user = UnifiedUser.objects.all_with_deleted().get(pk=user_id)
        
        # Simple direct updates
        allowed_fields = ["first_name", "last_name", "email", "phone", "country", "state", "city", "address", "bio"]
        updated_fields = []
        
        for field in allowed_fields:
            if field in request.data:
                setattr(user, field, request.data[field])
                updated_fields.append(field)
                
        if updated_fields:
            user.save(update_fields=updated_fields + ["updated_at"])
            
        logger.info("Admin %s updated user %s fields: %s", request.user.email, user.identifying_info, updated_fields)
        
        event_bus.emit_on_commit(
            "user.updated_by_admin",
            user_id=str(user.pk),
            admin_user_id=str(request.user.pk),
            fields=updated_fields
        )
        
        return success_response(
            data={"user_id": str(user.pk)},
            message="User account updated successfully."
        )

class AdminUserVerifyView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    @transaction.atomic
    def post(self, request, user_id, *args, **kwargs):
        if not (request.user.is_staff or request.user.role in ["admin", "super_admin"]):
            raise PermissionDenied("You do not have permission to perform this action.")
            
        user = UnifiedUser.objects.all_with_deleted().get(pk=user_id)
        if user.is_verified:
            raise ValidationError("User is already verified.")
            
        user.is_verified = True
        user.save(update_fields=["is_verified", "updated_at"])
        
        logger.info("Admin %s marked user %s as verified", request.user.email, user.identifying_info)
        
        event_bus.emit_on_commit(
            "user.verified_by_admin",
            user_id=str(user.pk),
            admin_user_id=str(request.user.pk)
        )
        
        return success_response(
            data={"user_id": str(user.pk), "is_verified": user.is_verified},
            message="User verification status updated to verified."
        )

class AdminUserForcePasswordResetView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    @transaction.atomic
    def post(self, request, user_id, *args, **kwargs):
        if not (request.user.is_staff or request.user.role in ["admin", "super_admin"]):
            raise PermissionDenied("You do not have permission to perform this action.")
            
        user = UnifiedUser.objects.all_with_deleted().get(pk=user_id)
        
        # Trigger reset flow
        logger.info("Admin %s triggered force password reset for user %s", request.user.email, user.identifying_info)
        
        event_bus.emit_on_commit(
            "user.force_password_reset",
            user_id=str(user.pk),
            admin_user_id=str(request.user.pk)
        )
        
        return success_response(
            data={"user_id": str(user.pk)},
            message="Password reset process successfully triggered for user."
        )

class AdminUserRoleUpdateView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    @transaction.atomic
    def post(self, request, user_id, *args, **kwargs):
        if not (request.user.is_staff or request.user.role in ["admin", "super_admin"]):
            raise PermissionDenied("You do not have permission to perform this action.")
            
        user = UnifiedUser.objects.all_with_deleted().get(pk=user_id)
        new_role = request.data.get("role")
        if not new_role:
            raise ValidationError("Role is required.")
            
        valid_roles = [choice[0] for choice in UnifiedUser.ROLE_CHOICES]
        if new_role not in valid_roles:
            raise ValidationError(f"Invalid role. Must be one of: {valid_roles}")
            
        old_role = user.role
        user.role = new_role
        user.save(update_fields=["role", "updated_at"])
        
        logger.info("Admin %s updated user %s role from %s to %s", request.user.email, user.identifying_info, old_role, new_role)
        
        event_bus.emit_on_commit(
            "user.role_updated_by_admin",
            user_id=str(user.pk),
            admin_user_id=str(request.user.pk),
            old_role=old_role,
            new_role=new_role
        )
        
        return success_response(
            data={"user_id": str(user.pk), "role": user.role},
            message="User role updated successfully."
        )
