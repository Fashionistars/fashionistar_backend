from django.urls import path

from createOrder import views as create_order



app_name = 'store'  # Add this line to specify the app namespace

urlpatterns = [

    # create oder process
    path('create-order/', create_order.CreateOrderView.as_view(), name='create-order'),  # Update name to 'create-order'
]