# apps/transactions/views.py
"""
Financial Module — Transaction Auditing & Dispute Views
=======================================================

Provides auditing endpoints for transaction history and management tools
for disputes and refunds.

Flow:
  1. Auditing (List and retrieve specific transaction records)
  2. Summary (Aggregate stats for inflows/outflows)
  3. Dispute Resolution (Initiate disputes or refunds for escrowed payments)
"""

from rest_framework import generics, status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response, error_response
from apps.transactions.models import Transaction
from apps.transactions.serializers import (
    DisputeCreateSerializer,
    RefundResponseSerializer,
    RefundSerializer,
    TransactionDisputeSerializer,
    TransactionSerializer,
    TransactionSummarySerializer,
)
from apps.transactions.services import DisputeService, TransactionQueryService
from apps.wallet.services import EscrowService


# ===========================================================================
# TRANSACTION AUDITING (LIST & DETAIL)
# ===========================================================================


class TransactionListView(generics.ListAPIView):
    """
    Retrieves a paginated list of transactions for the authenticated user.

    Flow:
      1. Filter transactions where user is either the initiator or recipient.
      2. Order by most recent first.
      3. Return standardized transaction objects.

    Status Codes:
      200 OK: Returns transaction list.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        return TransactionQueryService.for_user(self.request.user)


class TransactionDetailView(generics.RetrieveAPIView):
    """
    Retrieves granular details of a specific transaction ID.

    Security:
      - Enforces ownership check (user must be party to the transaction).

    Status Codes:
      200 OK: Returns transaction details.
      404 Not Found: Transaction doesn't exist or user lacks access.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSerializer
    lookup_url_kwarg = "transaction_id"
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get_queryset(self):
        return TransactionQueryService.for_user(self.request.user)


# ===========================================================================
# TRANSACTION ANALYTICS & SUMMARY
# ===========================================================================


class TransactionSummaryView(generics.GenericAPIView):
    """
    Aggregates financial performance statistics for the user's wallet.

    Flow:
      1. Sum all credits (inflow).
      2. Sum all debits (outflow).
      3. Count total volume of transactions.

    Status Codes:
      200 OK: Returns summary statistics.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = TransactionSummarySerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def get(self, request):
        summary = TransactionQueryService.summary_for_user(request.user)
        return success_response(
            data=summary,
            message="Transaction summary retrieved.",
        )


# ===========================================================================
# DISPUTE & REFUND MANAGEMENT
# ===========================================================================


class TransactionRefundView(generics.GenericAPIView):
    """
    Initiates a manual refund for an escrowed payment.

    Flow:
      1. Verify the transaction is currently held in Escrow.
      2. Reverse the hold back to the client's available balance.
      3. Log the refund event in the transaction history.

    Status Codes:
      200 OK: Refund successfully processed.
      400 Bad Request: Transaction not eligible for refund.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = RefundSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, transaction_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            hold = EscrowService.refund_escrow(
                hold_reference=serializer.validated_data["hold_reference"],
                idempotency_key=request.headers.get("Idempotency-Key", ""),
            )
            return success_response(
                data={"hold_reference": hold.reference, "status": hold.status},
                message="Refund initiated successfully.",
            )
        except Exception as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)


class TransactionDisputeView(generics.GenericAPIView):
    """
    Opens a formal dispute case for a specific transaction.

    Flow:
      1. Client submits reason and disputed amount.
      2. Backend freezes related escrow funds if applicable.
      3. Notify admin/vendor of the open dispute.

    Status Codes:
      201 Created: Dispute case opened.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = DisputeCreateSerializer
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    def post(self, request, transaction_id):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            dispute = DisputeService.create_dispute(
                user=request.user,
                transaction_id=transaction_id,
                reason=serializer.validated_data["reason"],
                amount=serializer.validated_data["amount"],
            )
            return success_response(
                data=TransactionDisputeSerializer(dispute).data,
                message="Dispute created successfully.",
                status=status.HTTP_201_CREATED,
            )
        except Exception as exc:
            return error_response(message=str(exc), status=status.HTTP_400_BAD_REQUEST)
