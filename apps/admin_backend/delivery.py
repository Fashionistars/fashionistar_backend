# apps/admin_backend/delivery.py
# Django Packages
from django.shortcuts import get_object_or_404
from rest_framework import generics, status
from drf_spectacular.utils import extend_schema

# Models
from store.models import CartOrder
from apps.admin_backend.serializers import DeliveryStatusUpdateSerializer
from apps.common.renderers import CustomJSONRenderer, success_response


class DeliveryStatusUpdateView(generics.GenericAPIView):
    """
    POST /admin_backend/delivery/<order_id>/update/
    Industrial-grade view for updating order delivery status and tracking ID.
    """
    renderer_classes = [CustomJSONRenderer]
    serializer_class = DeliveryStatusUpdateSerializer
    permission_classes = [IsAuthenticated]
    queryset = CartOrder.objects.all()
    lookup_field = 'id'
    lookup_url_kwarg = 'order_id'

    @extend_schema(
        summary="Update Delivery Status",
        description="Updates the delivery status and tracking ID for a specific order.",
        responses={200: DeliveryStatusUpdateSerializer}
    )
    def post(self, request, *args, **kwargs):
        order = self.get_object()
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        delivery_status = serializer.validated_data.get('delivery_status')
        tracking_id = serializer.validated_data.get('tracking_id')

        updated = False
        if delivery_status:
            order.delivery_status = delivery_status
            updated = True
        if tracking_id:
            order.tracking_id = tracking_id
            updated = True

        if updated:
            order.save()

        return success_response(
            message="Delivery status updated successfully."
        )
