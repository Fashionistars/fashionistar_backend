# apps/payment/admin_backend/urls.py
from django.urls import path
from .views import AdminRefundPaymentView

urlpatterns = [
    path("<str:payment_intent_id>/refund/", AdminRefundPaymentView.as_view(), name="admin-payment-refund"),
]
