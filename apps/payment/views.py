# apps/payment/views.py
"""
Financial Module — Payment Processing Views
===========================================

Handles Paystack integration for initializing transactions, verifying payments,
and managing transfer recipients. 

Flow:
  1. Initialize (Frontend calls PaystackInitializeView)
  2. Redirect (User pays via Paystack)
  3. Verify (Webhook or manual VerifyView call)
"""

from django.core.exceptions import ValidationError
from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import generics, status
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.response import Response

from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.payment.selectors import get_payment_intent_for_user_reference
from apps.payment.serializers import (
    CashConfirmationConfirmSerializer,
    CashConfirmationCreateSerializer,
    CashConfirmationResendSerializer,
    PaymentIntentSerializer,
    PaystackBanksResponseSerializer,
    PaystackInitializeSerializer,
    PaystackTransferRecipientSerializer,
    PaystackVerifySerializer,
    PaystackWebhookSerializer,
    TransferRecipientCreateSerializer,
    WalletFundPaymentSerializer,
)
from apps.payment.cash_service import CashOrderService
from apps.payment.services import (
    PaymentIntentService,
    PaystackClient,
    PaystackWebhookService,
    TransferRecipientService,
)


# ===========================================================================
# POST /api/v1/payment/paystack/initialize/
# ===========================================================================


class PaystackInitializeView(generics.GenericAPIView):
    """
    Initializes a Paystack transaction and creates a PaymentIntent record.

    Flow:
      1. Receive amount and metadata from frontend.
      2. Check idempotency to prevent double-charging.
      3. Call Paystack API to get an authorization URL.
      4. Store the reference and link it to the current User.

    Status Codes:
      201 Created: Initialization successful, returns Paystack URL.
      400 Bad Request: Invalid payload or Paystack provider error.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PaystackInitializeSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            intent = PaymentIntentService.initialize_paystack(
                user=request.user,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                **serializer.validated_data,
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data=PaymentIntentSerializer(intent).data,
            message="Payment initialized successfully.",
            status=status.HTTP_201_CREATED,
        )


# ===========================================================================
# GET /api/v1/payment/paystack/verify/<reference>/
# ===========================================================================


class PaystackVerifyView(generics.GenericAPIView):
    """
    Verifies the status of a specific Paystack transaction reference.

    Flow:
      1. Frontend provides the reference after user payment.
      2. Backend queries Paystack Verify API.
      3. If success, updates PaymentIntent and associated Wallet/Order.
      4. Returns final state to the frontend.

    Status Codes:
      200 OK: Payment confirmed and processed.
      400 Bad Request: Payment failed or reference not found.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PaystackVerifySerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request, reference: str):
        try:
            response = PaystackClient.verify_payment(reference)
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)

        if response.get("status") and (response.get("data") or {}).get("status") == "success":
            try:
                intent = get_payment_intent_for_user_reference(request.user, reference)
                PaymentIntentService.mark_success(intent, response)
                return success_response(
                    data=PaymentIntentSerializer(intent).data,
                    message="Payment verified successfully.",
                )
            except request.user.payment_intents.model.DoesNotExist:
                return error_response(message="Payment reference not found locally.", status=status.HTTP_404_NOT_FOUND)

        return error_response(
            message="Payment is not successful.",
            errors={"provider_response": response},
            status=status.HTTP_400_BAD_REQUEST,
        )


# ===========================================================================
# POST /api/v1/payment/paystack/webhook/
# ===========================================================================


@method_decorator(csrf_exempt, name="dispatch")
class PaystackWebhookView(generics.GenericAPIView):
    """
    Asynchronous handler for Paystack webhook notifications.

    Flow:
      1. Paystack sends a signed POST request.
      2. Verify signature using environment secret.
      3. Process the event (charge.success, transfer.success, etc.).
      4. Ensure idempotency via reference tracking.

    Status Codes:
      200 OK: Webhook accepted.
      401 Unauthorized: Invalid signature.
    """
    permission_classes = [AllowAny]
    serializer_class = PaystackWebhookSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        try:
            webhook = PaystackWebhookService.process(
                raw_payload=request.body,
                signature=request.headers.get("X-Paystack-Signature", ""),
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_401_UNAUTHORIZED)

        return success_response(
            data={"processed": webhook.processed},
            message="Webhook received and processed.",
        )


# ===========================================================================
# GET /api/v1/payment/paystack/banks/
# ===========================================================================


class PaystackBanksView(generics.GenericAPIView):
    """
    Retrieves the list of supported Nigerian banks for transfers.

    Flow:
      1. Query Paystack Banks list endpoint.
      2. Filter or format as needed.
      3. Return to frontend for bank selection in withdrawal flows.

    Status Codes:
      200 OK: Returns list of banks.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = PaystackBanksResponseSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        try:
            banks_data = PaystackClient.list_banks()
            return success_response(
                data=banks_data,
                message="Banks retrieved successfully from Paystack."
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)


# ===========================================================================
# POST /api/v1/payment/paystack/recipient/
# ===========================================================================


class PaystackTransferRecipientView(generics.GenericAPIView):
    """
    Creates a Transfer Recipient on Paystack for withdrawals.

    Flow:
      1. User provides bank code and account number.
      2. Backend calls Paystack to create a recipient.
      3. Store the recipient code for future transfer operations.

    Status Codes:
      201 Created: Recipient successfully registered.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TransferRecipientCreateSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            recipient = TransferRecipientService.create_for_user(
                user=request.user,
                idempotency_key=request.headers.get("Idempotency-Key", ""),
                **serializer.validated_data,
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data=PaystackTransferRecipientSerializer(recipient).data,
            message="Transfer recipient created successfully.",
            status=status.HTTP_201_CREATED,
        )


class WalletFundPaymentView(generics.GenericAPIView):
    """Shared order-payment and wallet-topup entrypoint."""

    permission_classes = [IsAuthenticated]
    serializer_class = WalletFundPaymentSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        payload = serializer.validated_data

        try:
            if payload["purpose"] == "order_payment":
                order = PaymentIntentService._get_order_for_payment(
                    user=request.user,
                    order_id=payload.get("order_id", ""),
                )
                PaymentIntentService._validate_order_payment_request(
                    order=order,
                    provider=payload["provider"],
                    payment_path=payload["payment_path"],
                    selected_percent=payload["selected_percent"],
                )
                # Ensure idempotency key is always set — if the client omits the
                # header, generate a deterministic fallback keyed to the exact
                # payment parameters so double-submit cannot create duplicate intents.
                idempotency_key = request.headers.get("Idempotency-Key") or (
                    f"view-order-payment:{request.user.pk}:{payload.get('order_id', '')}:"
                    f"{payload['provider']}:{payload['payment_path']}:{payload['selected_percent']}"
                )
                if payload["provider"] == "wallet":
                    intent, record = PaymentIntentService.pay_order_from_wallet(
                        user=request.user,
                        order=order,
                        selected_percent=payload["selected_percent"],
                        payment_path=payload["payment_path"],
                        idempotency_key=idempotency_key,
                        metadata=payload.get("metadata", {}),
                    )
                    return success_response(
                        data={
                            "intent": PaymentIntentSerializer(intent).data,
                            "order_id": str(order.pk),
                            "payment_record_id": str(record.pk) if record else "",
                            "authorization_url": "",
                        },
                        message="Wallet payment completed successfully.",
                        status=status.HTTP_201_CREATED,
                    )

                intent = PaymentIntentService.initialize_gateway_payment(
                    user=request.user,
                    order=order,
                    provider=payload["provider"],
                    selected_percent=payload["selected_percent"],
                    payment_path=payload["payment_path"],
                    currency=payload.get("currency", "NGN"),
                    idempotency_key=idempotency_key,
                    cash_payment_mode=payload.get("cash_payment_mode", order.cash_payment_mode_snapshot),
                    metadata=payload.get("metadata", {}),
                )
                return success_response(
                    data={
                        "intent": PaymentIntentSerializer(intent).data,
                        "order_id": str(order.pk),
                        "authorization_url": intent.authorization_url,
                    },
                    message="Payment initialized successfully.",
                    status=status.HTTP_201_CREATED,
                )

            intent = PaymentIntentService.initialize_paystack(
                user=request.user,
                amount=payload["amount"],
                purpose=payload["purpose"],
                currency=payload.get("currency", "NGN"),
                idempotency_key=idempotency_key,
                metadata=payload.get("metadata", {}),
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)

        return success_response(
            data={
                "intent": PaymentIntentSerializer(intent).data,
                "authorization_url": intent.authorization_url,
            },
            message="Payment initialized successfully.",
            status=status.HTTP_201_CREATED,
        )


class CashConfirmationCreateView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CashConfirmationCreateSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = CashOrderService.create_confirmation_token(
                order_id=serializer.validated_data["order_id"],
                client_user=request.user,
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=payload,
            message="Cash confirmation token created successfully.",
            status=status.HTTP_201_CREATED,
        )


class CashConfirmationResendView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CashConfirmationResendSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            token = CashOrderService.resend_token(
                serializer.validated_data["order_id"],
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data={"confirmation_token": token},
            message="Cash confirmation token resent successfully.",
        )


class CashConfirmationConfirmView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = CashConfirmationConfirmSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            payload = CashOrderService.confirm_cod_delivery(
                order_id=serializer.validated_data["order_id"],
                vendor_user=request.user,
                client_token=serializer.validated_data["client_token"],
            )
        except ValidationError as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
        return success_response(
            data=payload,
            message="Cash confirmation completed successfully.",
        )
