from rest_framework import generics, parsers, status
from rest_framework.renderers import (
    BrowsableAPIRenderer,
    JSONRenderer,
    MultiPartRenderer,
    StaticHTMLRenderer,
)

from apps.common.renderers import CustomJSONRenderer, success_response


class CatalogWriteMixin:
    """DRF generic-view hooks that route all writes through domain services."""

    service_class = None
    archive_message = "Catalog resource archived successfully."

    renderer_classes = [
        CustomJSONRenderer,
        BrowsableAPIRenderer,
        MultiPartRenderer,
        JSONRenderer,
        StaticHTMLRenderer,
    ]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)

    def perform_create(self, serializer):
        self.service_class.create(serializer=serializer, request=self.request)

    def perform_update(self, serializer):
        old_values = dict(self.get_serializer(self.get_object()).data)
        self.service_class.update(
            serializer=serializer,
            request=self.request,
            old_values=old_values,
        )

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        old_values = dict(self.get_serializer(instance).data)
        archived = self.service_class.archive(
            instance=instance,
            request=request,
            old_values=old_values,
        )
        return success_response(
            data={"id": str(archived.pk)},
            message=self.archive_message,
            status=status.HTTP_200_OK,
        )


class CatalogListCreateAPIView(CatalogWriteMixin, generics.ListCreateAPIView):
    pagination_class = None


class CatalogRetrieveUpdateDestroyAPIView(CatalogWriteMixin, generics.RetrieveUpdateDestroyAPIView):
    lookup_field = "slug"
