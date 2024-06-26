from django.urls import path
from . import views as userauths_views






urlpatterns = [
    # DeliveryContact URLs
    path('delivery-contact/', userauths_views.DeliveryContactListCreateView.as_view(), name='delivery-contact-list-create'),
    path('delivery-contact/<int:pk>/', userauths_views.DeliveryContactDetailView.as_view(), name='delivery-contact-detail'),

    # ShippingAddress URLs
    path('shipping-address/', userauths_views.ShippingAddressListCreateView.as_view(), name='shipping-address-list-create'),
    path('shipping-address/<int:pk>/', userauths_views.ShippingAddressDetailView.as_view(), name='shipping-address-detail'),
]
