# apps/authentication/apis/profile_views/sync_views.py
"""
Profile Views — Synchronous DRF (WSGI)

Endpoints:
  - UserProfileDetailView : GET/PATCH /api/v1/profile/me/
  - UserListView          : GET /api/v1/profile/users/ (admin only)
  - MeView                : GET /api/v1/auth/me/      (auth rehydration)

Architecture:
  - Views never touch ORM directly — selectors for reads, services for writes.
  - MeView uses MeSerializer for a strongly-typed, stable response
    contract that the frontend Zustand auth store depends on.
  - UserProfileDetailView delegates writes to update_user_profile().
"""
import logging
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.authentication.models import UnifiedUser
from apps.authentication.serializers.profile import (
    MeSerializer,
    ProtectedUserSerializer,
    UserProfileSerializer,
)
from apps.authentication.services.profile_service import (
    update_user_profile,
)
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response

logger = logging.getLogger(__name__)


# =============================================================================
# USER PROFILE DETAIL — Authenticated full profile (self)
# =============================================================================


class UserProfileDetailView(generics.RetrieveUpdateAPIView):
    """
    GET  /api/v1/profile/me/ — Return authenticated user's full profile.
    PATCH /api/v1/profile/me/ — Partial update of authenticated user profile.

    GET  uses: UserProfileSerializer (all readable fields)
    PATCH uses: update_user_profile() service (guarded, validated writes)
    """
    serializer_class = UserProfileSerializer
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_object(self):
        """Return the requesting user object for profile operations."""
        return self.request.user

    @extend_schema(
        summary="Retrieve user profile",
        description="Returns the full profile details of the currently authenticated user.",
        responses={200: UserProfileSerializer}
    )
    def retrieve(self, request, *args, **kwargs):
        """Return user profile wrapped in success_response."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(
            data=serializer.data,
            message="Profile retrieved successfully."
        )

    @extend_schema(
        summary="Update user profile",
        description="Partially updates the profile of the currently authenticated user.",
        request=UserProfileSerializer,
        responses={200: UserProfileSerializer}
    )
    def update(self, request, *args, **kwargs):
        """Update profile and return wrapped response."""
        partial = kwargs.pop('partial', False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)
        
        try:
            updated_user = update_user_profile(
                user=instance,
                data=serializer.validated_data,
            )
            return success_response(
                data=UserProfileSerializer(updated_user).data,
                message="Profile updated successfully."
            )
        except ValueError as exc:
            return error_response(
                message=str(exc),
                status=status.HTTP_400_BAD_REQUEST
            )
        except Exception as exc:
            logger.error(f"Profile update error: {exc}", exc_info=True)
            return error_response(
                message="An unexpected error occurred while updating your profile.",
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


# =============================================================================
# USER LIST — Admin-only
# =============================================================================


class UserListView(generics.ListAPIView):
    """
    GET /api/v1/profile/users/ — Admin-only list of all registered users.

    Returns ProtectedUserSerializer shape — no sensitive fields exposed.
    """
    serializer_class = ProtectedUserSerializer
    permission_classes = [IsAdminUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        return (
            UnifiedUser.objects.only(
                "id", "member_id", "email", "phone",
                "first_name", "last_name", "role", "auth_provider",
                "is_verified", "is_active", "is_staff",
                "avatar", "bio", "country", "state", "city", "address",
                "date_joined",
            ).order_by("-date_joined")
        )

    @extend_schema(
        summary="List all users",
        description="Returns a paginated list of all users. Admin only.",
        responses={200: ProtectedUserSerializer(many=True)}
    )
    def list(self, request, *args, **kwargs):
        """List users with standardized success response."""
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return success_response(
            data=serializer.data,
            message="Users list retrieved successfully."
        )


# =============================================================================
# ME VIEW — Auth rehydration (frontend SSR / Zustand)
# =============================================================================


class MeView(generics.RetrieveAPIView):
    """
    GET /api/v1/auth/me/

    Returns the authenticated user's full profile via MeSerializer.
    Used by useAuthHydration() to rehydrate Zustand on page refresh.

    Authorization: Bearer <access_token>
    Error 401: Not authenticated / token expired.

    Response shape (stable contract with frontend):
    {
        "user_id":          "uuid-string",
        "identifying_info": "email@example.com" | "+2348012345678",
        "member_id":        "FASTAR000001" | null,
        "email":            "email@example.com" | null,
        "phone":            "+2348012345678" | null,
        "first_name":       "John" | "",
        "last_name":        "Doe" | "",
        "role":             "client" | "vendor" | "staff" | ...,
        "auth_provider":    "email" | "phone" | "google",
        "is_verified":      true | false,
        "is_active":        true | false,
        "is_staff":         true | false,
        "avatar":           "https://res.cloudinary.com/..." | null,
        "bio":              "..." | "",
        "country":          "Nigeria" | "",
        "state":            "Lagos" | "",
        "city":             "Ikeja" | "",
        "address":          "..." | "",
        "date_joined":      "2024-01-15T10:30:00+00:00" | null,
        "last_login":       "2024-01-15T10:30:00+00:00" | null
    }
    """
    serializer_class = MeSerializer
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_object(self):
        """Return the requesting user object for serialization."""
        return self.request.user

    @extend_schema(
        responses={200: MeSerializer},
        summary="Get current user",
        description="Returns details of the currently authenticated user for frontend rehydration."
    )
    def retrieve(self, request, *args, **kwargs):
        """Return the authenticated user profile wrapped in success_response."""
        instance = self.get_object()
        serializer = self.get_serializer(instance)
        return success_response(
            data=serializer.data,
            message="User details retrieved successfully."
        )

