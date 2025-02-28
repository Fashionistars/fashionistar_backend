from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from rest_framework.permissions import IsAdminUser, AllowAny
from django.shortcuts import get_object_or_404
from admin_backend.models import Brand
from admin_backend.serializers import BrandSerializer





class BrandListView(APIView):
    """
    View to retrieve all brands.
    """
    permission_classes = (AllowAny,)

    def get(self, request):
        try:
            brands = Brand.objects.all()
            serializer = BrandSerializer(brands, many=True)
            return Response({"message": "Brands retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BrandDetailView(APIView):
    """
    View to retrieve a specific brand by its slug.
    """
    permission_classes = (AllowAny,)

    def get(self, request, slug):
        try:
            brand = get_object_or_404(Brand, slug=slug)
            serializer = BrandSerializer(brand)
            return Response({"message": "Brand retrieved successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BrandCreateView(APIView):
    """
    View to create a new brand.
    """
    permission_classes = (IsAdminUser,)

    def post(self, request):
        try:
            serializer = BrandSerializer(data=request.data)
            if serializer.is_valid():
                serializer.save(user=request.user)
                return Response({"message": "Brand created successfully.", "data": serializer.data}, status=status.HTTP_201_CREATED)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BrandUpdateView(APIView):
    """
    View to update an existing brand.
    """
    permission_classes = (IsAdminUser,)

    def put(self, request, slug):
        try:
            brand = get_object_or_404(Brand, slug=slug)
            serializer = BrandSerializer(brand, data=request.data, partial=True)
            if serializer.is_valid():
                serializer.save()
                return Response({"message": "Brand updated successfully.", "data": serializer.data}, status=status.HTTP_200_OK)
            return Response({"error": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class BrandDeleteView(APIView):
    """
    View to delete an existing brand.
    """
    permission_classes = (IsAdminUser,)

    def delete(self, request, slug):
        try:
            brand = get_object_or_404(Brand, slug=slug)
            brand.delete()
            return Response({"message": "Brand deleted successfully."}, status=status.HTTP_204_NO_CONTENT)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
