from django.urls import path

from store import views as storeviews




urlpatterns = [
    path('checkout/<int:cart_id>/', storeviews.CheckoutView.as_view(), name='checkout'),
    path('calculate-shipping/', storeviews.CalculateShippingView.as_view(), name='calculate-shipping'),
    path('calculate-service-fee/', storeviews.CalculateServiceFeeView.as_view(), name='calculate-service-fee'),
    path('delivery-contacts/', storeviews.DeliveryContactListCreateView.as_view(), name='delivery-contact-list-create'),
    path('delivery-contacts/<int:pk>/', storeviews.DeliveryContactDetailView.as_view(), name='delivery-contact-detail'),
    path('shipping-addresses/', storeviews.ShippingAddressListCreateView.as_view(), name='shipping-address-list-create'),
    path('shipping-addresses/<int:pk>/', storeviews.ShippingAddressDetailView.as_view(), name='shipping-address-detail'),
]


