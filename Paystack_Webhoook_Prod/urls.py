from django.urls import path
from Paystack_Webhoook_Prod.deposit import UserDepositView, UserVerifyDepositView
from Paystack_Webhoook_Prod.webhook import paystack_webhook_view

urlpatterns = [
    path('user/deposit/', UserDepositView.as_view()),
    path('user/deposit/verify/<str:reference>/', UserVerifyDepositView.as_view()),



    #########  INVISIBLE WEBHOOK, UNDER BACKGROUND CHECK FOR RETURNING TRNASACTION STAUTS IMMEDIATELY FROM PAYSTACK   ##########
    path('paystack/webhook/', paystack_webhook_view, name='paystack-webhook'),
]
