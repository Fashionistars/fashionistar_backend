from django.urls import path

from apps.catalog.apis.sync import (
    CatalogBrandDetailView,
    CatalogBrandListCreateView,
    CatalogCategoryDetailView,
    CatalogCategoryListCreateView,
    CatalogCollectionDetailView,
    CatalogCollectionListCreateView,
)

app_name = "catalog"

urlpatterns = [
    path("categories/", CatalogCategoryListCreateView.as_view(), name="category-list"),
    path("categories/<slug:slug>/", CatalogCategoryDetailView.as_view(), name="category-detail"),
    path("brands/", CatalogBrandListCreateView.as_view(), name="brand-list"),
    path("brands/<slug:slug>/", CatalogBrandDetailView.as_view(), name="brand-detail"),
    path("collections/", CatalogCollectionListCreateView.as_view(), name="collection-list"),
    path("collections/<slug:slug>/", CatalogCollectionDetailView.as_view(), name="collection-detail"),
]
