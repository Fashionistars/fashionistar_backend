from django.apps import apps
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated

from apps.admin_backend.serializers import DeliveryStatusUpdateSerializer
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response


def _get_cart_order_model():
    try:
        return apps.get_model("store", "CartOrder")
    except LookupError:
        return None


class DeliveryStatusUpdateView(generics.GenericAPIView):
    """
    POST /admin_backend/delivery/<order_id>/update/
    Temporary compatibility endpoint while order ownership migrates to apps/order.
    """

    renderer_classes = [CustomJSONRenderer]
    serializer_class = DeliveryStatusUpdateSerializer
    permission_classes = [IsAuthenticated]
    lookup_field = "id"
    lookup_url_kwarg = "order_id"

    @extend_schema(
        summary="Update Delivery Status",
        description="Updates delivery status for legacy orders while apps/order migration is pending.",
        responses={200: DeliveryStatusUpdateSerializer},
    )
    def post(self, request, *args, **kwargs):
        CartOrder = _get_cart_order_model()
        if CartOrder is None:
            return error_response(
                message="Delivery status updates are temporarily unavailable while the order domain migration is completing.",
                code="order_domain_migration_pending",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            order = CartOrder.objects.get(id=kwargs.get(self.lookup_url_kwarg))
        except CartOrder.DoesNotExist:
            return error_response(
                message="Order not found.",
                code="order_not_found",
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        delivery_status = serializer.validated_data.get("delivery_status")
        tracking_id = serializer.validated_data.get("tracking_id")

        update_fields = []
        if delivery_status:
            order.delivery_status = delivery_status
            update_fields.append("delivery_status")
        if tracking_id:
            order.tracking_id = tracking_id
            update_fields.append("tracking_id")

        if update_fields:
            order.save(update_fields=update_fields)

        return success_response(message="Delivery status updated successfully.")
