from django.core.exceptions import ValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response

from apps.payment.models import PaymentIntent
from apps.payment.serializers import (
    PaymentIntentSerializer,
    PaystackInitializeSerializer,
    PaystackTransferRecipientSerializer,
    TransferRecipientCreateSerializer,
)
from apps.payment.services import PaystackClient, PaystackWebhookService, PaymentIntentService, TransferRecipientService


class PaystackInitializeView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PaystackInitializeSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        intent = PaymentIntentService.initialize_paystack(
            user=request.user,
            idempotency_key=request.headers.get("Idempotency-Key", ""),
            **serializer.validated_data,
        )
        return Response({"status": "success", "data": PaymentIntentSerializer(intent).data}, status=status.HTTP_201_CREATED)


class PaystackVerifyView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, reference: str):
        response = PaystackClient.verify_payment(reference)
        if response.get("status") and (response.get("data") or {}).get("status") == "success":
            intent = PaymentIntent.objects.get(reference=reference, user=request.user)
            PaymentIntentService.mark_success(intent, response)
            return Response({"status": "success", "data": PaymentIntentSerializer(intent).data})
        return Response({"status": "error", "message": "Payment is not successful.", "provider_response": response}, status=status.HTTP_400_BAD_REQUEST)


@method_decorator(csrf_exempt, name="dispatch")
class PaystackWebhookView(generics.GenericAPIView):
    permission_classes = [AllowAny]

    def post(self, request):
        try:
            webhook = PaystackWebhookService.process(
                raw_payload=request.body,
                signature=request.headers.get("X-Paystack-Signature", ""),
            )
        except ValidationError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_401_UNAUTHORIZED)
        return Response({"status": "success", "processed": webhook.processed})


class PaystackBanksView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response(PaystackClient.list_banks())


class PaystackTransferRecipientView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TransferRecipientCreateSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            recipient = TransferRecipientService.create_for_user(user=request.user, **serializer.validated_data)
        except ValidationError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "success", "data": PaystackTransferRecipientSerializer(recipient).data}, status=status.HTTP_201_CREATED)
