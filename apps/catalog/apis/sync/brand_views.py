from apps.catalog.apis.sync.base import CatalogListCreateAPIView, CatalogRetrieveUpdateDestroyAPIView
from apps.catalog.models import Brand
from apps.catalog.permissions import IsCatalogStaffOrReadOnly
from apps.catalog.selectors import CatalogSelector
from apps.catalog.serializers import CatalogBrandSerializer
from apps.catalog.services import BrandService
from apps.catalog.throttles import CatalogWriteThrottle


class CatalogBrandListCreateView(CatalogListCreateAPIView):
    serializer_class = CatalogBrandSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    throttle_classes = (CatalogWriteThrottle,)
    service_class = BrandService
    archive_message = "Catalog brand archived successfully."

    def get_queryset(self):
        if self.request.method == "GET":
            return CatalogSelector.brands()
        return Brand.objects.all().order_by("title")


class CatalogBrandDetailView(CatalogRetrieveUpdateDestroyAPIView):
    serializer_class = CatalogBrandSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    throttle_classes = (CatalogWriteThrottle,)
    service_class = BrandService
    archive_message = "Catalog brand archived successfully."

    def get_queryset(self):
        return Brand.objects.all()
