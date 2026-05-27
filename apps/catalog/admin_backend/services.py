# apps/catalog/admin_backend/services.py
import logging
from django.db import transaction
from apps.catalog.services.category_service import CategoryService
from apps.catalog.services.brand_service import BrandService
from apps.catalog.services.collection_service import CollectionService
from apps.catalog.services.blog_service import BlogService

logger = logging.getLogger(__name__)

@transaction.atomic
def admin_create_category_sync(serializer, request):
    return CategoryService.create(serializer=serializer, request=request)

@transaction.atomic
def admin_update_category_sync(serializer, request, old_values: dict):
    return CategoryService.update(serializer=serializer, request=request, old_values=old_values)

@transaction.atomic
def admin_archive_category_sync(instance, request, old_values: dict):
    return CategoryService.archive(instance=instance, request=request, old_values=old_values)

@transaction.atomic
def admin_create_brand_sync(serializer, request):
    return BrandService.create(serializer=serializer, request=request)

@transaction.atomic
def admin_update_brand_sync(serializer, request, old_values: dict):
    return BrandService.update(serializer=serializer, request=request, old_values=old_values)

@transaction.atomic
def admin_archive_brand_sync(instance, request, old_values: dict):
    return BrandService.archive(instance=instance, request=request, old_values=old_values)

@transaction.atomic
def admin_create_collection_sync(serializer, request):
    return CollectionService.create(serializer=serializer, request=request)

@transaction.atomic
def admin_update_collection_sync(serializer, request, old_values: dict):
    return CollectionService.update(serializer=serializer, request=request, old_values=old_values)

@transaction.atomic
def admin_archive_collection_sync(instance, request, old_values: dict):
    return CollectionService.archive(instance=instance, request=request, old_values=old_values)


@transaction.atomic
def admin_create_blog_post_sync(serializer, request):
    return BlogService.create(serializer=serializer, request=request)

@transaction.atomic
def admin_update_blog_post_sync(serializer, request, old_values: dict):
    return BlogService.update(serializer=serializer, request=request, old_values=old_values)

@transaction.atomic
def admin_archive_blog_post_sync(instance, request, old_values: dict):
    return BlogService.archive(instance=instance, request=request, old_values=old_values)


