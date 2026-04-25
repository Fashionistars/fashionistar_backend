from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.wallet.models import Wallet
from apps.wallet.serializers import (
    EscrowHoldSerializer,
    EscrowRefundSerializer,
    EscrowReleaseSerializer,
    WalletHoldSerializer,
    WalletPinChangeSerializer,
    WalletPinSetSerializer,
    WalletPinVerifySerializer,
    WalletSerializer,
)
from apps.wallet.services import EscrowService, WalletPinService, WalletProvisioningService

User = get_user_model()


def _idempotency_key(request) -> str:
    return request.headers.get("Idempotency-Key", "")


class MyWalletView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WalletSerializer

    def get(self, request):
        wallet = WalletProvisioningService.ensure_wallet(request.user)
        return Response({"status": "success", "data": self.get_serializer(wallet).data})


class WalletBalanceView(MyWalletView):
    pass


class WalletSetPinView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WalletPinSetSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        wallet = WalletPinService.set_pin(request.user, serializer.validated_data["pin"])
        return Response({"status": "success", "message": "Transaction PIN set.", "data": WalletSerializer(wallet).data})


class WalletVerifyPinView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WalletPinVerifySerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        valid = WalletPinService.verify_pin(request.user, serializer.validated_data["pin"])
        return Response({"status": "success", "data": {"valid": valid}})


class WalletChangePinView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = WalletPinChangeSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            wallet = WalletPinService.change_pin(
                request.user,
                serializer.validated_data["current_pin"],
                serializer.validated_data["new_pin"],
            )
        except ValidationError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "success", "message": "Transaction PIN changed.", "data": WalletSerializer(wallet).data})


class EscrowHoldView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EscrowHoldSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            hold = EscrowService.hold_order_payment(
                client_user=request.user,
                idempotency_key=_idempotency_key(request),
                **serializer.validated_data,
            )
        except ValidationError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "success", "data": WalletHoldSerializer(hold).data}, status=status.HTTP_201_CREATED)


class EscrowReleaseView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EscrowReleaseSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor_user = User.objects.get(pk=serializer.validated_data["vendor_user_id"])
        try:
            result = EscrowService.release_order_payment(
                hold_reference=serializer.validated_data["hold_reference"],
                vendor_user=vendor_user,
                commission_rate=serializer.validated_data["commission_rate"],
                idempotency_key=_idempotency_key(request),
            )
        except ValidationError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "success", "data": result})


class EscrowRefundView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = EscrowRefundSerializer

    def post(self, request):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            hold = EscrowService.refund_escrow(
                hold_reference=serializer.validated_data["hold_reference"],
                idempotency_key=_idempotency_key(request),
            )
        except ValidationError as exc:
            return Response({"status": "error", "message": str(exc)}, status=status.HTTP_400_BAD_REQUEST)
        return Response({"status": "success", "data": WalletHoldSerializer(hold).data})
