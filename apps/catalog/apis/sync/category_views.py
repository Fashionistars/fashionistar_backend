from apps.catalog.apis.sync.base import CatalogListCreateAPIView, CatalogRetrieveUpdateDestroyAPIView
from apps.catalog.models import Category
from apps.catalog.permissions import IsCatalogStaffOrReadOnly
from apps.catalog.selectors import CatalogSelector
from apps.catalog.serializers import CatalogCategorySerializer
from apps.catalog.services import CategoryService
from apps.catalog.throttles import CatalogWriteThrottle


class CatalogCategoryListCreateView(CatalogListCreateAPIView):
    serializer_class = CatalogCategorySerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    throttle_classes = (CatalogWriteThrottle,)
    service_class = CategoryService
    archive_message = "Catalog category archived successfully."

    def get_queryset(self):
        if self.request.method == "GET":
            return CatalogSelector.categories()
        return Category.objects.all().order_by("name")


class CatalogCategoryDetailView(CatalogRetrieveUpdateDestroyAPIView):
    serializer_class = CatalogCategorySerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    throttle_classes = (CatalogWriteThrottle,)
    service_class = CategoryService
    archive_message = "Catalog category archived successfully."

    def get_queryset(self):
        return Category.objects.all()
