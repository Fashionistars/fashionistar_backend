from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from adrf.views import APIView as AsyncAPIView
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.models import UnifiedUser
from asgiref.sync import sync_to_async
from apps.authentication.serializers import UserSerializer # Need to create this
import logging

class UserProfileDetailView(AsyncAPIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def get(self, request):
        serializer = UserSerializer(request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    async def patch(self, request):
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        is_valid = await sync_to_async(serializer.is_valid)()
        if is_valid:
            await sync_to_async(serializer.save)()
            return Response(serializer.data, status=status.HTTP_200_OK)
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

class UserListView(AsyncAPIView):
    permission_classes = [IsAdminUser]
    renderer_classes = [CustomJSONRenderer]

    async def get(self, request):
        users = await sync_to_async(list)(UnifiedUser.objects.all())
        serializer = UserSerializer(users, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)
