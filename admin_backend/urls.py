from django.urls import path
from rest_framework.routers import DefaultRouter

from .views import BrandViewSet, CategoryViewSet, CollectionsViewSet

router = DefaultRouter()
router.register(r"categories", CategoryViewSet, basename="category")
router.register(r"brands", BrandViewSet, basename="brand")
router.register(r"collections", CollectionsViewSet, basename="collection")

app_name = "admin_backend"

urlpatterns = [
    path(
        "admin/category/create/",
        CategoryViewSet.as_view({"post": "create"}),
        name="category-create",
    ),
    path(
        "admin/category/all/",
        CategoryViewSet.as_view({"get": "list"}),
        name="category-list",
    ),
    path(
        "admin/category/<slug:slug>/",
        CategoryViewSet.as_view({"get": "retrieve"}),
        name="category-detail",
    ),
    path(
        "admin/category/<slug:slug>/update/",
        CategoryViewSet.as_view({"put": "update", "patch": "partial_update"}),
        name="category-update",
    ),
    path(
        "admin/category/<slug:slug>/delete/",
        CategoryViewSet.as_view({"delete": "destroy"}),
        name="category-delete",
    ),
    path(
        "admin/brands/create/",
        BrandViewSet.as_view({"post": "create"}),
        name="brand-create",
    ),
    path(
        "admin/brands/all/",
        BrandViewSet.as_view({"get": "list"}),
        name="brand-list",
    ),
    path(
        "admin/brands/<slug:slug>/",
        BrandViewSet.as_view({"get": "retrieve"}),
        name="brand-detail",
    ),
    path(
        "admin/brands/<slug:slug>/update/",
        BrandViewSet.as_view({"put": "update", "patch": "partial_update"}),
        name="brand-update",
    ),
    path(
        "admin/brands/<slug:slug>/delete/",
        BrandViewSet.as_view({"delete": "destroy"}),
        name="brand-delete",
    ),
    path(
        "admin/collections/create/",
        CollectionsViewSet.as_view({"post": "create"}),
        name="collection-create",
    ),
    path(
        "admin/collections/all/",
        CollectionsViewSet.as_view({"get": "list"}),
        name="collection-list",
    ),
    path(
        "admin/collections/<slug:slug>/",
        CollectionsViewSet.as_view({"get": "retrieve"}),
        name="collection-detail",
    ),
    path(
        "admin/collections/<slug:slug>/update/",
        CollectionsViewSet.as_view({"put": "update", "patch": "partial_update"}),
        name="collection-update",
    ),
    path(
        "admin/collections/<slug:slug>/delete/",
        CollectionsViewSet.as_view({"delete": "destroy"}),
        name="collection-delete",
    ),
]

urlpatterns += router.urls
