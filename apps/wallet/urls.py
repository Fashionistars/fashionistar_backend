from django.urls import path

from apps.wallet.views import (
    EscrowHoldView,
    EscrowRefundView,
    EscrowReleaseView,
    MyWalletView,
    WalletBalanceView,
    WalletChangePinView,
    WalletSetPinView,
    WalletVerifyPinView,
)

app_name = "wallet"

urlpatterns = [
    path("me/", MyWalletView.as_view(), name="me"),
    path("balance/", WalletBalanceView.as_view(), name="balance"),
    path("pin/set/", WalletSetPinView.as_view(), name="pin-set"),
    path("pin/verify/", WalletVerifyPinView.as_view(), name="pin-verify"),
    path("pin/change/", WalletChangePinView.as_view(), name="pin-change"),
    path("escrow/hold/", EscrowHoldView.as_view(), name="escrow-hold"),
    path("escrow/release/", EscrowReleaseView.as_view(), name="escrow-release"),
    path("refund/", EscrowRefundView.as_view(), name="refund"),
]
