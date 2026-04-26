from apps.catalog.apis.sync.base import CatalogListCreateAPIView, CatalogRetrieveUpdateDestroyAPIView
from apps.catalog.models import Collections
from apps.catalog.permissions import IsCatalogStaffOrReadOnly
from apps.catalog.selectors import CatalogSelector
from apps.catalog.serializers import CatalogCollectionSerializer
from apps.catalog.services import CollectionService
from apps.catalog.throttles import CatalogWriteThrottle


class CatalogCollectionListCreateView(CatalogListCreateAPIView):
    serializer_class = CatalogCollectionSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    throttle_classes = (CatalogWriteThrottle,)
    service_class = CollectionService
    archive_message = "Catalog collection archive request recorded successfully."

    def get_queryset(self):
        if self.request.method == "GET":
            return CatalogSelector.collections()
        return Collections.objects.all().order_by("-created_at")


class CatalogCollectionDetailView(CatalogRetrieveUpdateDestroyAPIView):
    serializer_class = CatalogCollectionSerializer
    permission_classes = (IsCatalogStaffOrReadOnly,)
    throttle_classes = (CatalogWriteThrottle,)
    service_class = CollectionService
    archive_message = "Catalog collection archive request recorded successfully."

    def get_queryset(self):
        return Collections.objects.all()
