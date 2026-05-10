from apps.catalog.apis.sync.base import CatalogListCreateAPIView, CatalogRetrieveUpdateDestroyAPIView
from apps.catalog.models import BlogPost
from apps.catalog.permissions import IsCatalogStaffOrReadOnly
from apps.catalog.selectors import CatalogSelector
from apps.catalog.serializers import CatalogBlogPostSerializer
from apps.catalog.services import BlogService
from apps.catalog.throttles import CatalogWriteThrottle


class CatalogBlogListCreateView(CatalogListCreateAPIView):
    serializer_class = CatalogBlogPostSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    throttle_classes = (CatalogWriteThrottle,)
    service_class = BlogService
    archive_message = "Catalog blog post archived successfully."

    def get_queryset(self):
        include_drafts = bool(
            getattr(self.request.user, "is_staff", False)
            or getattr(self.request.user, "is_superuser", False)
        )
        if self.request.method == "GET":
            return CatalogSelector.blog_posts(include_drafts=include_drafts)
        return BlogPost.objects.select_related("author", "category").prefetch_related("gallery_media")


class CatalogBlogDetailView(CatalogRetrieveUpdateDestroyAPIView):
    serializer_class = CatalogBlogPostSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    throttle_classes = (CatalogWriteThrottle,)
    service_class = BlogService
    archive_message = "Catalog blog post archived successfully."

    def get_queryset(self):
        include_drafts = bool(
            getattr(self.request.user, "is_staff", False)
            or getattr(self.request.user, "is_superuser", False)
        )
        if include_drafts:
            return BlogPost.objects.select_related("author", "category").prefetch_related("gallery_media")
        return CatalogSelector.blog_posts(include_drafts=False)
