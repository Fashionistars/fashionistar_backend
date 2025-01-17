from django.urls import path
from .deposit import UserDepositView, UserVerifyDepositView
from Paystack_Webhoook_Prod.webhook import paystack_webhook_view

urlpatterns = [
    path('user/deposit/', UserDepositView.as_view()),
    path('user/deposit/verify/<str:reference>/', UserVerifyDepositView.as_view()),
    path('paystack/webhook/', paystack_webhook_view, name='paystack-webhook'),
]