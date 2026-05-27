# apps/catalog/admin_backend/urls.py
from django.urls import path
from apps.catalog.admin_backend.views import (
    AdminCategoryCreateView,
    AdminCategoryUpdateView,
    AdminCategoryArchiveView,
    AdminBrandCreateView,
    AdminBrandUpdateView,
    AdminBrandArchiveView,
    AdminCollectionCreateView,
    AdminCollectionUpdateView,
    AdminCollectionArchiveView,
    AdminBlogPostCreateView,
    AdminBlogPostUpdateView,
    AdminBlogPostArchiveView,
)

app_name = "admin_catalog"


urlpatterns = [
    # Categories
    path("categories/create/", AdminCategoryCreateView.as_view(), name="category-create"),
    path("categories/<category_id>/update/", AdminCategoryUpdateView.as_view(), name="category-update"),
    path("categories/<category_id>/archive/", AdminCategoryArchiveView.as_view(), name="category-archive"),

    # Brands
    path("brands/create/", AdminBrandCreateView.as_view(), name="brand-create"),
    path("brands/<brand_id>/update/", AdminBrandUpdateView.as_view(), name="brand-update"),
    path("brands/<brand_id>/archive/", AdminBrandArchiveView.as_view(), name="brand-archive"),

    # Collections
    path("collections/create/", AdminCollectionCreateView.as_view(), name="collection-create"),
    path("collections/<collection_id>/update/", AdminCollectionUpdateView.as_view(), name="collection-update"),
    path("collections/<collection_id>/archive/", AdminCollectionArchiveView.as_view(), name="collection-archive"),

    # Blogs
    path("blog/create/", AdminBlogPostCreateView.as_view(), name="blog-create"),
    path("blog/<post_id>/update/", AdminBlogPostUpdateView.as_view(), name="blog-update"),
    path("blog/<post_id>/archive/", AdminBlogPostArchiveView.as_view(), name="blog-archive"),
]


