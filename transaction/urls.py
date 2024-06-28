from django.urls import path
from . import views
from django.views.decorators.csrf import csrf_exempt

urlpatterns = [
    path('initiate-payment/', csrf_exempt(views.InitiatePayment.as_view()), name='initiate_payment'),
    path('payment/callback/', views.PaymentCallback.as_view(), name='payment_callback'),
]
