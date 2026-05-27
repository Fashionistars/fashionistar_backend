# apps/payment/admin_backend/views.py
import logging
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status

from apps.admin_backend.permissions import IsSuperuserOnly
from apps.payment.models import PaymentIntent
from apps.payment.admin_backend.serializers import AdminRefundPaymentSerializer
from apps.payment.admin_backend.services import admin_refund_payment_intent

logger = logging.getLogger(__name__)

class AdminRefundPaymentView(APIView):
    permission_classes = [IsSuperuserOnly]

    def post(self, request, payment_intent_id):
        try:
            intent = PaymentIntent.objects.get(id=payment_intent_id)
        except PaymentIntent.DoesNotExist:
            return Response({"status": "error", "message": "Payment intent not found."}, status=status.HTTP_404_NOT_FOUND)
            
        serializer = AdminRefundPaymentSerializer(data=request.data)
        if not serializer.is_valid():
            return Response({"status": "error", "errors": serializer.errors}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            admin_refund_payment_intent(
                payment_intent_id=payment_intent_id,
                admin_user=request.user,
                amount=serializer.validated_data["amount"],
                reason=serializer.validated_data.get("reason", ""),
            )
            return Response({"status": "success", "message": "Refund processed successfully."}, status=status.HTTP_200_OK)
        except Exception as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
