from django.urls import path

from apps.transactions.views import (
    TransactionDetailView,
    TransactionDisputeView,
    TransactionListView,
    TransactionRefundView,
    TransactionSummaryView,
)

app_name = "transactions"

urlpatterns = [
    path("", TransactionListView.as_view(), name="list"),
    path("summary/", TransactionSummaryView.as_view(), name="summary"),
    path("<uuid:transaction_id>/", TransactionDetailView.as_view(), name="detail"),
    path("<uuid:transaction_id>/refund/", TransactionRefundView.as_view(), name="refund"),
    path("<uuid:transaction_id>/dispute/", TransactionDisputeView.as_view(), name="dispute"),
]
