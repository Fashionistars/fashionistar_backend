# apps/catalog/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.db import transaction

from apps.admin_backend.permissions import IsAdminUser
from apps.catalog.models.category import Category
from apps.catalog.models.brand import Brand
from apps.catalog.models.collection import Collections
from apps.catalog.admin_backend.serializers import (
    AdminCategoryWriteSerializer,
    AdminBrandWriteSerializer,
    AdminCollectionWriteSerializer,
)
from apps.catalog.admin_backend.services import (
    admin_create_category_sync,
    admin_update_category_sync,
    admin_archive_category_sync,
    admin_create_brand_sync,
    admin_update_brand_sync,
    admin_archive_brand_sync,
    admin_create_collection_sync,
    admin_update_collection_sync,
    admin_archive_collection_sync,
)

logger = logging.getLogger(__name__)

class AdminCategoryCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = AdminCategoryWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            category = admin_create_category_sync(serializer=serializer, request=request)
            return Response({"status": "success", "data": {"id": str(category.id), "name": category.name}}, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminCategoryUpdateView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, category_id):
        try:
            category = Category.objects.get(id=category_id, is_deleted=False)
        except Category.DoesNotExist:
            return Response({"status": "error", "message": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        
        old_values = {"name": category.name, "description": category.description, "active": category.active}
        serializer = AdminCategoryWriteSerializer(category, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            admin_update_category_sync(serializer=serializer, request=request, old_values=old_values)
            return Response({"status": "success", "message": "Category updated successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminCategoryArchiveView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, category_id):
        try:
            category = Category.objects.get(id=category_id, is_deleted=False)
        except Category.DoesNotExist:
            return Response({"status": "error", "message": "Category not found."}, status=status.HTTP_404_NOT_FOUND)
        
        old_values = {"active": category.active}
        try:
            admin_archive_category_sync(instance=category, request=request, old_values=old_values)
            return Response({"status": "success", "message": "Category archived successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class AdminBrandCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = AdminBrandWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            brand = admin_create_brand_sync(serializer=serializer, request=request)
            return Response({"status": "success", "data": {"id": str(brand.id), "title": brand.title}}, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminBrandUpdateView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, brand_id):
        try:
            brand = Brand.objects.get(id=brand_id, is_deleted=False)
        except Brand.DoesNotExist:
            return Response({"status": "error", "message": "Brand not found."}, status=status.HTTP_404_NOT_FOUND)
        
        old_values = {"title": brand.title, "description": brand.description, "active": brand.active}
        serializer = AdminBrandWriteSerializer(brand, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            admin_update_brand_sync(serializer=serializer, request=request, old_values=old_values)
            return Response({"status": "success", "message": "Brand updated successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminBrandArchiveView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, brand_id):
        try:
            brand = Brand.objects.get(id=brand_id, is_deleted=False)
        except Brand.DoesNotExist:
            return Response({"status": "error", "message": "Brand not found."}, status=status.HTTP_404_NOT_FOUND)
        
        old_values = {"active": brand.active}
        try:
            admin_archive_brand_sync(instance=brand, request=request, old_values=old_values)
            return Response({"status": "success", "message": "Brand archived successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)


class AdminCollectionCreateView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request):
        serializer = AdminCollectionWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            collection = admin_create_collection_sync(serializer=serializer, request=request)
            return Response({"status": "success", "data": {"id": str(collection.id), "name": collection.name}}, status=status.HTTP_201_CREATED)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminCollectionUpdateView(APIView):
    permission_classes = [IsAdminUser]

    def patch(self, request, collection_id):
        try:
            collection = Collections.objects.get(id=collection_id, is_deleted=False)
        except Collections.DoesNotExist:
            return Response({"status": "error", "message": "Collection not found."}, status=status.HTTP_404_NOT_FOUND)
        
        old_values = {"name": collection.name, "description": collection.description, "active": collection.active}
        serializer = AdminCollectionWriteSerializer(collection, data=request.data, partial=True)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
        try:
            admin_update_collection_sync(serializer=serializer, request=request, old_values=old_values)
            return Response({"status": "success", "message": "Collection updated successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)

class AdminCollectionArchiveView(APIView):
    permission_classes = [IsAdminUser]

    def post(self, request, collection_id):
        try:
            collection = Collections.objects.get(id=collection_id, is_deleted=False)
        except Collections.DoesNotExist:
            return Response({"status": "error", "message": "Collection not found."}, status=status.HTTP_404_NOT_FOUND)
        
        old_values = {"active": collection.active}
        try:
            admin_archive_collection_sync(instance=collection, request=request, old_values=old_values)
            return Response({"status": "success", "message": "Collection archived successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
