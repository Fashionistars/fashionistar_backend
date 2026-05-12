# Django Packages
from django.shortcuts import get_object_or_404
from django.db.models import Q
from django.conf import settings
from django.core.exceptions import ObjectDoesNotExist

# Restframework Packages
from rest_framework.response import Response
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework import status

# Serializers
from ShopCart.serializers import CartSerializer

# Models
from userauths.models import User
from ShopCart.models import Cart
from store.models import Product

# Others Packages
from decimal import Decimal


class CartApiView(generics.ListCreateAPIView):
    
    '''
    =============================   Explanation for the Frontend Developer          =================================
            
            cart/view/: Use this endpoint to view or create a new cart. It handles both viewing existing carts and adding new products to the cart.

            To create a new cart or add items to an existing cart, send a POST request to this endpoint with the following payload:
            {
                "cart_id": "string",  # Unique identifier for the cart
                "user_id": "integer or null",  # Optional, if the cart is associated with a user
                "products": [
                    {
                        "product": "integer",  # ID of the product to add
                        "qty": "integer",  # Quantity of the product
                        "price": "decimal",  # Price of the product
                        "size": "string",  # Optional, size of the product
                        "color": "string"  # Optional, color of the product
                    },
                    ...
                ]
            }

            These comments should help the frontend developer understand the purpose and usage of each endpoint, ensuring they can correctly implement the necessary API calls.
                
    '''
    
    serializer_class = CartSerializer
    queryset = Cart.objects.all()
    permission_classes = (AllowAny,)

    def create(self, request, *args, **kwargs):
        try:
            payload = request.data
            products = payload.get('products', [])
            cart_id = payload.get('cart_id')
            user_id = payload.get('user_id')

            # Fetch user if user_id is provided
            user = None
            if user_id and user_id != "undefined":
                user = get_object_or_404(User, id=user_id)

            total_sub_total = Decimal(0.0)
            total_total = Decimal(0.0)

            for product_data in products:
                product_id = product_data.get('product')
                qty = product_data.get('qty')
                price = product_data.get('price')
                size = product_data.get('size')
                color = product_data.get('color')

                # Fetch product
                product = get_object_or_404(Product, id=product_id, status="published")

                # Fetch or create cart instance for the specific product
                cart, created = Cart.objects.get_or_create(cart_id=cart_id, product=product, defaults={'user': user})

                if not created:
                    # If the cart item already exists, update the quantity and price
                    cart.qty += int(qty)
                    cart.price = Decimal(price)  # Assuming price remains the same for simplicity
                else:
                    # If new cart item, set the quantity and price
                    cart.qty = int(qty)
                    cart.price = Decimal(price)

                # Update cart attributes
                cart.sub_total = cart.price * cart.qty
                cart.size = size
                cart.color = color
                cart.cart_id = cart_id
                cart.user = user

                # Update the total amounts
                total_sub_total += cart.sub_total
                total_total += cart.sub_total  # Assuming no additional charges

                cart.save()

            return Response({"message": "Cart updated successfully", "sub_total": total_sub_total, "total": total_total}, status=status.HTTP_200_OK)

        except ObjectDoesNotExist as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def list(self, request, *args, **kwargs):
        return super().list(request, *args, **kwargs)
    

    
class CartListView(generics.ListAPIView):

    '''
    =============================   Explanation for the Frontend Developer          =================================
            
            cart/list/<str:cart_id>/: Use this endpoint to list all items in a specific cart identified by cart_id.
            cart/list/<str:cart_id>/<int:user_id>/: Similar to the previous endpoint, but additionally filters the cart items for a specific user identified by user_id.

            These comments should help the frontend developer understand the purpose and usage of each endpoint, ensuring they can correctly implement the necessary API calls.
                
    '''
    serializer_class = CartSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        cart_id = self.kwargs['cart_id']
        user_id = self.kwargs.get('user_id')

        if user_id is not None:
            user = get_object_or_404(User, id=user_id)
            queryset = Cart.objects.filter(Q(user=user, cart_id=cart_id) | Q(user=user))
        else:
            queryset = Cart.objects.filter(cart_id=cart_id)
        
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            serializer = CartSerializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ObjectDoesNotExist as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def get_cart_total(self, cart_items):
        total_qty = sum(item.qty for item in cart_items)
        total_price = sum(item.sub_total for item in cart_items)
        return total_qty, total_price

    def get(self, request, *args, **kwargs):
        try:
            cart_items = self.get_queryset()
            total_qty, total_price = self.get_cart_total(cart_items)
            data = {
                "total_quantity": total_qty,
                "total_price": total_price,
                "cart_items": CartSerializer(cart_items, many=True).data
            }
            return Response(data, status=status.HTTP_200_OK)
        except ObjectDoesNotExist as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    

class CartTotalView(generics.ListAPIView):
    '''
    =============================   Explanation for the Frontend Developer          =================================
            
            cart/total/<str:cart_id>/: Use this endpoint to get the total values (e.g., subtotal, total) for a specific cart identified by cart_id.
            cart/total/<str:cart_id>/<int:user_id>/: Similar to the previous endpoint, but additionally filters the total values for a specific user identified by user_id.

            These comments should help the frontend developer understand the purpose and usage of each endpoint, ensuring they can correctly implement the necessary API calls.
                
    '''
    serializer_class = CartSerializer
    permission_classes = (AllowAny,)

    def get_queryset(self):
        cart_id = self.kwargs['cart_id']
        user_id = self.kwargs.get('user_id')

        if user_id is not None:
            user = get_object_or_404(User, id=user_id)
            queryset = Cart.objects.filter(cart_id=cart_id, user=user)
        else:
            queryset = Cart.objects.filter(cart_id=cart_id)
        
        return queryset

    def list(self, request, *args, **kwargs):
        try:
            queryset = self.get_queryset()
            serializer = CartSerializer(queryset, many=True)
            return Response(serializer.data, status=status.HTTP_200_OK)
        except ObjectDoesNotExist as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    def get_total_values(self, cart_items):
        total_sub_total = sum(item.sub_total for item in cart_items)
        total_total = sum(item.total for item in cart_items)
        return total_sub_total, total_total

    def get(self, request, *args, **kwargs):
        try:
            cart_items = self.get_queryset()
            total_sub_total, total_total = self.get_total_values(cart_items)
            data = {
                "sub_total": total_sub_total,
                "total": total_total
            }
            return Response(data, status=status.HTTP_200_OK)
        except ObjectDoesNotExist as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    

class CartDetailView(generics.RetrieveAPIView):
        '''
    =============================   Explanation for the Frontend Developer          =================================
 
            cart/detail/<str:cart_id>/: Use this endpoint to get detailed information about a specific cart identified by cart_id.
            cart/detail/<str:cart_id>/<int:user_id>/: Similar to the previous endpoint, but additionally filters the cart details for a specific user identified by user_id.

            These comments should help the frontend developer understand the purpose and usage of each endpoint, ensuring they can correctly implement the necessary API calls.
                
    '''
    
        # Define the serializer class for the view
        serializer_class = CartSerializer
        # Specify the lookup field for retrieving objects using 'cart_id'
        lookup_field = 'cart_id'

        # Add a permission class for the view
        permission_classes = (AllowAny,)


        def get_queryset(self):
            # Get 'cart_id' and 'user_id' from the URL kwargs
            cart_id = self.kwargs['cart_id']
            user_id = self.kwargs.get('user_id')  # Use get() to handle cases where 'user_id' is not present

            if user_id is not None:
                # If 'user_id' is provided, filter the queryset by both 'cart_id' and 'user_id'
                user = User.objects.get(id=user_id)
                queryset = Cart.objects.filter(cart_id=cart_id, user=user)
            else:
                # If 'user_id' is not provided, filter the queryset by 'cart_id' only
                queryset = Cart.objects.filter(cart_id=cart_id)

            return queryset

        def get(self, request, *args, **kwargs):
            # Get the queryset of cart items based on 'cart_id' and 'user_id' (if provided)
            queryset = self.get_queryset()

            # Initialize sums for various cart item attributes
            total_sub_total = 0.0
            total_total = 0.0

            # Iterate over the queryset of cart items to calculate cumulative sums
            for cart_item in queryset:
                # Calculate the cumulative shipping, tax, service_fee, and total values
                
                total_sub_total += float(self.calculate_sub_total(cart_item))
                total_total += round(float(self.calculate_total(cart_item)), 2)

            # Create a data dictionary to store the cumulative values
            data = {
                
                'sub_total': total_sub_total,
                'total': total_total,
            }

            # Return the data in the response
            return Response(data)

       
        def calculate_sub_total(self, cart_item):
            # Implement your service fee calculation logic here for a single cart item
            # Example: Calculate based on service type, cart total, etc.
            return cart_item.sub_total

        def calculate_total(self, cart_item):
            # Implement your total calculation logic here for a single cart item
            # Example: Sum of sub_total, shipping, tax, and service_fee
            return cart_item.total    




class CartUpdateApiView(generics.UpdateAPIView):


    '''
       =============================   Explanation for the Frontend Developer          =================================

            cart/update/<str:cart_id>/<int:item_id>/: Use this endpoint to update the details of a specific item in the cart identified by item_id.
            cart/update/<str:cart_id>/<int:item_id>/<int:user_id>/: Similar to the previous endpoint, but additionally checks if the item belongs to a specific user identified by user_id.

            These comments should help the frontend developer understand the purpose and usage of each endpoint, ensuring they can correctly implement the necessary API calls.
                
    '''
    serializer_class = CartSerializer
    queryset = Cart.objects.all()
    permission_classes = (AllowAny,)
    lookup_field = 'item_id'  # Including lookup_field

    def get_object(self, cart_id, item_id, user_id=None):
        # Check if user_id is provided
        if user_id is not None:
            # Fetch the User object
            user = get_object_or_404(User, id=user_id)
            # Fetch the Cart item associated with cart_id, item_id, and user
            cart_item = get_object_or_404(Cart, cart_id=cart_id, id=item_id, user=user)
        else:
            # Fetch the Cart item associated with cart_id and item_id only
            cart_item = get_object_or_404(Cart, cart_id=cart_id, id=item_id)
        return cart_item

    def update(self, request, *args, **kwargs):
        try:
            cart_id = kwargs.get('cart_id')
            user_id = request.data.get('user_id')
            items = request.data.get('items', [])

            updated_items = []

            for item in items:
                item_id = item.get('item_id')
                # Fetch the cart item using the get_object method
                cart_item = self.get_object(cart_id, item_id, user_id)

                # Update the cart item attributes
                qty = item.get('qty', cart_item.qty)
                price = Decimal(item.get('price', cart_item.price))
                size = item.get('size', cart_item.size)
                color = item.get('color', cart_item.color)

                cart_item.qty = int(qty)
                cart_item.price = price
                cart_item.size = size
                cart_item.color = color
                cart_item.sub_total = cart_item.price * cart_item.qty

                # Save the updated cart item
                cart_item.save()
                updated_items.append(cart_item)

            # Return the response with updated cart items
            return Response(
                {"message": "Cart items updated successfully", "items": CartSerializer(updated_items, many=True).data},
                status=status.HTTP_200_OK
            )
        except ObjectDoesNotExist as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)



class CartItemDeleteView(generics.DestroyAPIView):

    '''
    =============================   Explanation for the Frontend Developer          =================================
        
            cart/delete/<str:cart_id>/<int:item_id>/: Use this endpoint to delete a specific item identified by item_id from a specific cart identified by cart_id.
            cart/delete/<str:cart_id>/<int:item_id>/<int:user_id>/: Similar to the previous endpoint, but additionally checks if the item belongs to a specific user identified by user_id.

            These comments should help the frontend developer understand the purpose and usage of each endpoint, ensuring they can correctly implement the necessary API calls.
    '''
    queryset = Cart.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = CartSerializer
    lookup_field = 'item_id'  

    def get_object(self):
        cart_id = self.kwargs['cart_id']
        item_id = self.kwargs['item_id']
        user_id = self.kwargs.get('user_id')

        if user_id is not None:
            user = get_object_or_404(User, id=user_id)
            cart_item = get_object_or_404(Cart, cart_id=cart_id, id=item_id, user=user)
        else:
            cart_item = get_object_or_404(Cart, cart_id=cart_id, id=item_id)

        return cart_item

    def delete(self, request, *args, **kwargs):
        try:
            cart_item = self.get_object()
            cart_item.delete()
            return Response({"message": "Cart item deleted successfully"}, status=status.HTTP_204_NO_CONTENT)
        except ObjectDoesNotExist as e:
            return Response({"error": str(e)}, status=status.HTTP_404_NOT_FOUND)
        except ValidationError as e:
            return Response({"error": e.detail}, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            return Response({"error": str(e)}, status=status.HTTP_403_FORBIDDEN)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)






