from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404
from admin_backend.models import Collections
from admin_backend.serializers import CollectionsSerializer

class CollectionsListView(APIView):
    """
    View to retrieve all collections.
    """
    permission_classes = (AllowAny,)

    def get(self, request):
        try:
            collections = Collections.objects.all()
            serializer = CollectionsSerializer(collections, many=True)
            return Response({"message": "Collections retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CollectionsDetailView(APIView):
    """
    View to retrieve a specific collection by its slug.
    """
    permission_classes = (AllowAny,)

    def get(self, request, slug):
        try:
            collection = get_object_or_404(Collections, slug=slug)
            serializer = CollectionsSerializer(collection)
            return Response({"message": "Collection retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CollectionsCreateView(APIView):
    """
    View to create a new collection.
    """
    permission_classes = (IsAdminUser,)

    def post(self, request):
        try:
            serializer = CollectionsSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(user=request.user)
                return Response({"message": "Collection created successfully.", "data": serializer.data}, status=status.HTTP_201_CREATED)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CollectionsUpdateView(APIView):
    """
    View to update an existing collection.
    """
    permission_classes = (IsAdminUser,)

    def put(self, request, slug):
        try:
            collection = get_object_or_404(Collections, slug=slug)
            serializer = CollectionsSerializer(collection, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({"message": "Collection updated successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CollectionsDeleteView(APIView):
    """
    View to delete an existing collection.
    """
    permission_classes = (IsAdminUser,)

    def delete(self, request, slug):
        try:
            collection = get_object_or_404(Collections, slug=slug)
            collection.delete()
            return Response({"message": "Collection deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
