# apps/authentication/apis/profile_views/async_views.py

import logging
import asyncio
from rest_framework import status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from adrf.views import APIView
from apps.common.renderers import CustomJSONRenderer
from apps.authentication.models import UnifiedUser
from apps.authentication.serializers import UserSerializer

class UserProfileDetailView(APIView):
    permission_classes = [IsAuthenticated]
    renderer_classes = [CustomJSONRenderer]

    async def get(self, request):
        # Serialize in thread to avoid blocking loop if object graph checks occur
        serializer = await asyncio.to_thread(UserSerializer, request.user)
        return Response(serializer.data, status=status.HTTP_200_OK)

    async def patch(self, request):
        # 1. Initialize Serializer
        serializer = UserSerializer(request.user, data=request.data, partial=True)
        
        # 2. Validate in Thread check DB if unique constraints exist
        await asyncio.to_thread(serializer.is_valid, raise_exception=True)
        
        # 3. Save in Thread (since serializer.save is sync)
        await asyncio.to_thread(serializer.save)
        
        return Response(serializer.data, status=status.HTTP_200_OK)

class UserListView(APIView):
    permission_classes = [IsAdminUser]
    renderer_classes = [CustomJSONRenderer]

    async def get(self, request):
        # Native Async Query
        users = [u async for u in UnifiedUser.objects.all()]
        
        # Serialize list
        # Passing list of objects to serializer
        serializer = await asyncio.to_thread(UserSerializer, users, many=True)
        
        return Response(serializer.data, status=status.HTTP_200_OK)
