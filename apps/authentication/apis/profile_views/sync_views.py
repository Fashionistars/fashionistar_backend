# apps/authentication/apis/profile_views/sync_views.py
"""
Profile Views — Synchronous DRF (WSGI)

Exports:
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

from rest_framework import generics, status
from rest_framework.permissions import IsAdminUser, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.authentication.models import UnifiedUser
from apps.authentication.serializers.profile import (
    MeSerializer,
    ProtectedUserSerializer,
    UserProfileSerializer,
)
from apps.authentication.services.profile_service import (
    get_me_profile,
    update_user_profile,
)
from apps.common.renderers import CustomJSONRenderer

logger = logging.getLogger(__name__)


# =============================================================================
# USER PROFILE DETAIL — Authenticated full profile (self)
# =============================================================================


class UserProfileDetailView(APIView):
    """
    GET  /api/v1/profile/me/ — Return authenticated user's full profile.
    PATCH /api/v1/profile/me/ — Partial update of authenticated user profile.

    GET  uses: UserProfileSerializer (all readable fields)
    PATCH uses: update_user_profile() service (guarded, validated writes)
    """

    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        serializer = UserProfileSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UserProfileSerializer(
            request.user, data=request.data, partial=True
        )
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        try:
            updated_user = update_user_profile(
                user=request.user,
                data=serializer.validated_data,
            )
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

        out = UserProfileSerializer(updated_user)
        return Response(out.data, status=status.HTTP_200_OK)


# =============================================================================
# USER LIST — Admin-only
# =============================================================================


class UserListView(APIView):
    """
    GET /api/v1/profile/users/ — Admin-only list of all registered users.

    Returns ProtectedUserSerializer shape — no sensitive fields exposed.
    """

    permission_classes = [IsAdminUser]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        users = (
            UnifiedUser.objects.only(
                "id", "member_id", "email", "phone",
                "first_name", "last_name", "role", "auth_provider",
                "is_verified", "is_active", "is_staff",
                "avatar", "bio", "country", "state", "city", "address",
                "date_joined",
            ).order_by("-date_joined")
        )
        serializer = ProtectedUserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


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

    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]
    serializer_class = MeSerializer

    def get(self, request, *args, **kwargs):
        """Return the requesting user's profile via MeSerializer."""
        serializer = MeSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)
