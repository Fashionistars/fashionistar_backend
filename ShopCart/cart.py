###################################################################################

# ==============================================================================================================
# THIS PARTICULAR ENDPOINTS WILL BE PAID ATTENTION TO LATER KNOW IF I AM GOING TO CHERY PICK ANYTHING FROM IT IN ORDER T0 UPDATE MY CART MODEL

# ====================================================================================================


















from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.views import APIView
from django.shortcuts import get_object_or_404

from store.models import Product, CartOrder, CartOrderItem
from store.serializers import CartSerializer, CartOrderItemSerializer #All new models, please change
from userauths.models import User
from vendor.utils import fetch_user_and_vendor

# Get logger for application
application_logger = logging.getLogger('application')

"""API endpoint for creating a new product"""
def create_cart_id(request):
    """
       Create Cart_ID code to verify its the user when its client

        1- check for the code in request, if it is the case, we use the one on the request
        2 - else generate it
        3- check the code if is exists on any Cart_ID from database to ensure is not been used on new cart
    """
    code = shortuuid.uuid()
    if 'Cart_ID' in request.session:
        code = request.session['Cart_ID']
    else:
        request.session['Cart_ID'] = code

    return code

class AddToCart(APIView):
    """
    API endpoint for clients to add products to their shopping cart.
     *   *URL:* /api/client/cart/add/
        *   *Method:* POST
        *   *Authentication:* No authentication required, usable for all.
           *   *Request Body (JSON):*
                json
                 {
                   "product_id":  "b8b873bb-22b9-47f5-b0be-68668d077d60",  // Product the client wants to add to the cart.
                   "qty": 2,  // Qty of the product
                   "cart_id": shortuuid.uuid() // Generated in Frondend or Database
                 }
            
         *   *Response (JSON):*
                *   On success (HTTP 201 created):
                        json
                        {
                            "message": "PRODUCT added to cart." // If add to cart is great!
                           }
                       
                *   On failure (HTTP 400 or 404):
                     json
                     {
                         "error": "Error message" // Message if the profile could not be found or the user is not a client.
                     }
                   Possible Error Messages:
                  * "You do not have permission to perform this action.": If the user is not a client
                  * "You must assign quantity to the item you are about to order"// Error Message when their is no quantity.
                 *  "Cart_ID not found, or already in used"// When it can’t catch if code for to verify

    """
    def post(self, request):
        """
        Used: Adding a product to the cart and generating any errors to catch a new create a new to be created, the steps were followed well all times and created from our code.
        """
         # Retrieve code and payload from the request
        cart_id = create_cart_key(request)
        payload = request.data

         # Catch the request or it may come with error
        try:
             qty = payload['qty']
             product_id = payload['product_id']

         # If any of them throw an error it will direct and to try and look for the right input or to contact and ask for the input,
         #We had added it to "" An error occurred, please check your input or contact support. {e}"" in this scenario
        except KeyError as e:
               application_logger.error(f"Missing a required field: {str(e)}")
               return Response({'error': f'You must provide {str(e)}'}, status=status.HTTP_400_BAD_REQUEST)

         # Test it, to see and make sure, if the product does not exist
        try:
            product = Product.objects.get(id=payload['product_id'], in_stock=True)
        except Product.DoesNotExist:
            application_logger.error(f"Product with id {product_id} does not exist.")
            return Response({'error': 'You must choose a product to add to cart'}, status=status.HTTP_404_NOT_FOUND)
         
         # If all Test went through, then run a New Cart
         #Also do not forget if it was the request, it all works fine
        try:
            CartOrder.objects.create(product=product, qty=qty, cart_id=cart_id)
            application_logger.info(f"{product.title} Added product to cart with the Qty {qty}")
            return Response({'message': f"{product.title} Added product to cart with the Qty {qty}"}, status=status.HTTP_201_CREATED)
        except Exception as e:
             application_logger.error(f"An unexpected error, Check your input or to be contacted.")
             return Response({'error': f"An error occurred, please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CartItemDeleteView(generics.DestroyAPIView):
    """
    API endpoint for clients to delete their bank account details.
      *   *URL:* /api/client/cart/delete/<str:cart_id>/<int:item_id>/
      *   *Method:* DELETE
      *   *Authentication:* No authentication required, for all.
       *   *Response (JSON):*
              *  On success (HTTP 204 No Content):
                      json
                        {} // No content
                      
                *  On failure (HTTP 404 Not Found):
                      json
                         {
                            "error": "Error message" // Error message detailing the failure
                         }
                    
                     Possible error messages:
                     *   "Cart not found": If no cart iten was found to user.
                     *   "Failed to delete": Please to try one more time in oreder to get help!
    """
    serializer_class = CartSerializer
    permission_classes = (AllowAny, )

    def destroy(self, request, cart_id, item_id, *args, **kwargs):
        """
         Handles the deletion of a cart item
        """
        try:
          cart_item = CartOrder.objects.get(cart_id=cart_id, product__id=item_id)
          cart_item.delete()

          application_logger.info(f"An cart with {self.kwargs['cart_id']} bank details deleted for user")
          return Response(status=status.HTTP_204_NO_CONTENT)
        except CartOrder.DoesNotExist:
             application_logger.error(f"Cart not found with id {cart_id} with the {item_id} by user")
             return Response({'error': 'An error occurred by cart, please try again later !'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
           return Response({'error': f'An error occurred to your account : {e}'}, status=status.HTTP_400_BAD_REQUEST)

class CartUpdateApiView(generics.UpdateAPIView):

    '''
    APIView which is using to make update to a created cart item.
    It also test it if the user and the details is working perfectly and giving the most unique and robust system on his time!
    '''
    serializer_class = CartSerializer
    queryset = CartOrder.objects.all()
    permission_classes = (AllowAny,)
   

    # To do the update on product detail and to save in the system
    def update(self, request, cart_id, item_id, *args, **kwargs):
         # Initialize the message to make great returns
         message = f"You account for client has been tested perfect {self.kwargs['item_id']} and from this card code {cart_id}"

        # Main the to do, to make sure the function is working and also by checking the user of what is he from the code, before entering
        # All try is for the purpose of the client side and to not brake any model that is here
         try:
              qty = request.data['qty']
             # The base of the model, where you can look out.
              try:
                  cart_item =  CartOrder.objects.get(cart_id=cart_id, product__id=item_id)
                  cart_item.qty = qty
                  cart_item.sub_total = cart_item.price * cart_item.qty
                  cart_item.save()
                  application_logger.info(f"CartItem with {self.kwargs['item_id']} updated by user")
                  # Used now to return a meassage to display to user that it was well created.
                  return Response({
                      "message": message
                       }, status=status.HTTP_200_OK)
              except Exception as e:
                return Response({"error": f"Product not found"}, status=status.HTTP_404_NOT_FOUND)
                # With all try, it makes more solid to the to do
         except Exception as e:
            # Here are where the error management that all has been tested in API.
            return Response({"error": f"Please check your input or contact support. {e}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

class CartClearView(generics.DestroyAPIView):
    """
    API endpoint for vendors to delete their bank account details.
      *   *URL:* /api/client/cart/delete/<str:cart_id>/<int:item_id>/
      *   *Method:* DELETE
      *   *Authentication:* All methods public for the new approach or what we call no autentication need
       *   *Response (JSON):*
              *  On success (HTTP 204 No Content):
                      json
                        {} // No content
                      
                *  On failure (HTTP 404 Not Found):
                      json
                         {
                            "error": "Error message" // Error message detailing the failure
                         }
                    
                     Possible error messages:
                     *   "Cart not found": If no cart iten was found to user.
                     *   "Failed to delete": Please to try one more time in oreder to get help!
    """
    serializer_class = CartSerializer
    permission_classes = (AllowAny,)
    

    # to delete the data, need the item_id, 
    def destroy(self, request, cart_id, *args, **kwargs):
        """
        Handles the delete request for the bank details.
        """
        #Here is set all try for every time is been requested. If it does not have what is wanted.
        try:
          #The code check for cart item and not if user, as you see to catch all what is done.
          cart_item = CartOrder.objects.filter(cart_id=cart_id)
          cart_item.delete()
          application_logger.info(f" All Cart id {cart_id}  bank details deleted")
          return Response(status=status.HTTP_204_NO_CONTENT)
        except CartOrder.DoesNotExist:
             application_logger.error(f"Cart not found with id {cart_id} or item")
             return Response({'error': 'Cart id  or product for cart not found'}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while deleting cart with id {cart_id}")
            return Response({'error': f'An error occurred to your cart, please check if the code or connect support : {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)

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
