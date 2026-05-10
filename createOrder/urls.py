from django.urls import path

from createOrder import order as create_order



app_name = 'createOrder'  # Add this line to specify the app namespace

urlpatterns = [

    # create oder process
    path('create-order/', create_order.CreateOrderView.as_view(), name='create-order'),  # Update name to 'create-order'
    path('order/success/', create_order.OrderSuccessView.as_view(), name='order-success'),
]