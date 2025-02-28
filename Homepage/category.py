from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404
from admin_backend.models import Category
from admin_backend.serializers import CategorySerializer

# Similarly, create views for Category and Brand models
class CategoryListView(APIView):
    """
    View to retrieve all categories.
    """
    permission_classes = (AllowAny,)

    def get(self, request):
        try:
            categories = Category.objects.all()
            serializer = CategorySerializer(categories, many=True)
            return Response({"message": "Categories retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CategoryDetailView(APIView):
    """
    View to retrieve a specific category by its slug.
    """
    permission_classes = (AllowAny,)

    def get(self, request, slug):
        try:
            category = get_object_or_404(Category, slug=slug)
            serializer = CategorySerializer(category)
            return Response({"message": "Category retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CategoryCreateView(APIView):
    """
    View to create a new category.
    """
    permission_classes = (AllowAny,)

    def post(self, request):
        try:
            serializer = CategorySerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(user=request.user)
                return Response({"message": "Category created successfully.", "data": serializer.data}, status=status.HTTP_201_CREATED)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CategoryUpdateView(APIView):
    """
    View to update an existing category.
    """
    permission_classes = (AllowAny,)

    def put(self, request, slug):
        try:
            category = get_object_or_404(Category, slug=slug)
            serializer = CategorySerializer(category, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({"message": "Category updated successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CategoryDeleteView(APIView):
    """
    View to delete an existing category.
    """
    permission_classes = (AllowAny,)

    def delete(self, request, slug):
        try:
            category = get_object_or_404(Category, slug=slug)
            category.delete()
            return Response({"message": "Category deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

