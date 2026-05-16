from django.urls import path

from apps.payment.views import (
    CashConfirmationConfirmView,
    CashConfirmationCreateView,
    CashConfirmationResendView,
    PaystackBanksView,
    PaystackInitializeView,
    PaystackTransferRecipientView,
    PaystackVerifyView,
    PaystackWebhookView,
    WalletFundPaymentView,
)

app_name = "payment"

urlpatterns = [
    path("wallet/fund/", WalletFundPaymentView.as_view(), name="wallet-fund"),
    path("cash/create/", CashConfirmationCreateView.as_view(), name="cash-create"),
    path("cash/resend-token/", CashConfirmationResendView.as_view(), name="cash-resend-token"),
    path("cash/confirm/", CashConfirmationConfirmView.as_view(), name="cash-confirm"),
    path("paystack/initialize/", PaystackInitializeView.as_view(), name="paystack-initialize"),
    path("paystack/verify/<str:reference>/", PaystackVerifyView.as_view(), name="paystack-verify"),
    path("paystack/webhook/", PaystackWebhookView.as_view(), name="paystack-webhook"),
    path("banks/", PaystackBanksView.as_view(), name="banks"),
    path("transfer-recipient/", PaystackTransferRecipientView.as_view(), name="transfer-recipient"),
]
