from django.urls import path

from apps.payment.views import (
    PaystackBanksView,
    PaystackInitializeView,
    PaystackTransferRecipientView,
    PaystackVerifyView,
    PaystackWebhookView,
)

app_name = "payment"

urlpatterns = [
    path("paystack/initialize/", PaystackInitializeView.as_view(), name="paystack-initialize"),
    path("paystack/verify/<str:reference>/", PaystackVerifyView.as_view(), name="paystack-verify"),
    path("paystack/webhook/", PaystackWebhookView.as_view(), name="paystack-webhook"),
    path("banks/", PaystackBanksView.as_view(), name="banks"),
    path("transfer-recipient/", PaystackTransferRecipientView.as_view(), name="transfer-recipient"),
]
