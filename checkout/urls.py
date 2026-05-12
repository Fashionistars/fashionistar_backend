from django.urls import path

from checkout import views as store_views



app_name = 'checkout'  # Add this line to specify the app namespace

urlpatterns = [
    # service fee, shipping address and delivery contact API Endpoints
    path('checkout/<int:cart_id>/', store_views.CheckoutView.as_view(), name='checkout'),


    path('calculate-shipping/', store_views.CalculateShippingView.as_view(), name='calculate-shipping'),
    path('calculate-service-fee/', store_views.CalculateServiceFeeView.as_view(), name='calculate-service-fee'),
    path('delivery-contacts/', store_views.DeliveryContactListCreateView.as_view(), name='delivery-contact-list-create'),
    path('delivery-contacts/<int:pk>/', store_views.DeliveryContactDetailView.as_view(), name='delivery-contact-detail'),
    path('shipping-addresses/', store_views.ShippingAddressListCreateView.as_view(), name='shipping-address-list-create'),
    path('shipping-addresses/<int:pk>/', store_views.ShippingAddressDetailView.as_view(), name='shipping-address-detail'),


]




