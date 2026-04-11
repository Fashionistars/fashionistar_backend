# fix_profile_views.py — force-write the correct profile_views/sync_views.py

content = """\
# apps/authentication/apis/profile_views/sync_views.py
\"\"\"
Profile Views \u2014 Synchronous DRF (WSGI)

Exports:
  - UserProfileDetailView : GET/PATCH /api/v1/profile/me/
  - UserListView          : GET /api/v1/profile/users/ (admin only)
  - MeView                : GET /api/v1/auth/me/      (auth rehydration)
\"\"\"

import logging

from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.views import APIView
from rest_framework.renderers import BrowsableAPIRenderer
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.models import UnifiedUser
from apps.authentication.serializers import UserSerializer

logger = logging.getLogger(__name__)


class UserProfileDetailView(APIView):
    \"\"\"
    GET  /api/v1/profile/me/ \u2014 Return authenticated user full profile via serializer.
    PATCH /api/v1/profile/me/ \u2014 Partial update of authenticated user profile.
    \"\"\"
    permission_classes = [IsAuthenticated]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        if serializer.is_valid():
            serializer.save()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class UserListView(APIView):
    \"\"\"
    GET /api/v1/profile/users/ \u2014 Admin-only list of all registered users.
    \"\"\"
    permission_classes = [IsAdminUser]
    renderer_classes   = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        users = UnifiedUser.objects.all()
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550
# ME VIEW \u2014 Authenticated user profile (for frontend SSR rehydration)
# \u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550\u2550

class MeView(generics.RetrieveAPIView):
    \"\"\"
    GET /api/v1/auth/me/

    Returns the authenticated user's full profile.
    Used by useAuthHydration() to rehydrate Zustand on page refresh.

    Authorization: Bearer <access_token>
    Error 401: Not authenticated / token expired.
    \"\"\"
    permission_classes = [IsAuthenticated]
    renderer_classes   = [CustomJSONRenderer]

    def get(self, request, *args, **kwargs):
        \"\"\"Return the requesting user's profile from the JWT token claim.\"\"\"
        user = request.user
        return Response(
            {
                "id":          str(user.id),
                "member_id":   user.member_id,
                "email":       user.email,
                "phone":       str(user.phone) if user.phone else None,
                "first_name":  user.first_name,
                "last_name":   user.last_name,
                "role":        user.role,
                "is_verified": user.is_verified,
                "is_staff":    user.is_staff,
                "avatar":      user.avatar,
                "date_joined": user.date_joined.isoformat() if user.date_joined else None,
            },
            status=status.HTTP_200_OK,
        )
"""

with open('apps/authentication/apis/profile_views/sync_views.py', 'w', encoding='utf-8') as f:
    f.write(content)

print('SUCCESS: profile_views/sync_views.py written correctly')
print('Lines:', len(content.splitlines()))

# Verify imports
assert 'from rest_framework import generics' in content, 'generics import missing!'
assert 'class MeView' in content, 'MeView missing!'
assert 'class UserProfileDetailView' in content, 'UserProfileDetailView missing!'
print('All assertions passed.')
