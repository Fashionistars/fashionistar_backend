from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from apps.transactions.models import Transaction
from apps.transactions.serializers import (
    DisputeCreateSerializer,
    RefundSerializer,
    TransactionDisputeSerializer,
    TransactionSerializer,
)
from apps.transactions.services import DisputeService, TransactionQueryService
from apps.wallet.services import EscrowService


class TransactionListView(generics.ListAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSerializer

    def get_queryset(self):
        return TransactionQueryService.for_user(self.request.user)


class TransactionDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSerializer
    lookup_url_kwarg = "transaction_id"

    def get_queryset(self):
        return TransactionQueryService.for_user(self.request.user)


class TransactionSummaryView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        return Response({"status": "success", "data": TransactionQueryService.summary_for_user(request.user)})


class TransactionRefundView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = RefundSerializer

    def post(self, request, transaction_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        hold = EscrowService.refund_escrow(
            hold_reference=serializer.validated_data["hold_reference"],
            idempotency_key=request.headers.get("Idempotency-Key", ""),
        )
        return Response({"status": "success", "data": {"hold_reference": hold.reference, "status": hold.status}})


class TransactionDisputeView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = DisputeCreateSerializer

    def post(self, request, transaction_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dispute = DisputeService.create_dispute(
            user=request.user,
            transaction_id=transaction_id,
            reason=serializer.validated_data["reason"],
            amount=serializer.validated_data["amount"],
        )
        return Response({"status": "success", "data": TransactionDisputeSerializer(dispute).data}, status=status.HTTP_201_CREATED)
