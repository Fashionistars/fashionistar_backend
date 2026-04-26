from decimal import Decimal

from django.apps import apps
from drf_spectacular.utils import extend_schema
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated

from apps.admin_backend.serializers import AdminProfitSerializer
from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import error_response, success_response


def _get_cart_order_model():
    try:
        return apps.get_model("store", "CartOrder")
    except LookupError:
        return None


class AdminProfitView(generics.GenericAPIView):
    renderer_classes = [CustomJSONRenderer]
    permission_classes = [IsAuthenticated]
    serializer_class = AdminProfitSerializer

    @extend_schema(
        summary="Calculate Admin Profit",
        description="Calculates 10% commission profit from legacy orders while apps/order migration is pending.",
        responses={200: AdminProfitSerializer},
    )
    def get(self, request, *args, **kwargs):
        if not request.user.is_staff:
            return error_response(
                message="You do not have permission to view this resource.",
                code="permission_denied",
                status=status.HTTP_403_FORBIDDEN,
            )

        CartOrder = _get_cart_order_model()
        if CartOrder is None:
            return error_response(
                message="Admin profit is temporarily unavailable while the order domain migration is completing.",
                code="order_domain_migration_pending",
                status=status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        total_profit = Decimal("0.0")
        for order in CartOrder.objects.all():
            total_profit += order.total * Decimal("0.1")

        return success_response(
            data={"total_profit": total_profit},
            message="Profit calculated successfully.",
        )
