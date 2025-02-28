from rest_framework import generics
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.response import Response
from rest_framework import status
from rest_framework.exceptions import PermissionDenied, NotFound
import logging
from rest_framework.parsers import MultiPartParser, FormParser

from userauths.models import Profile
from customer.serializers import ProfileSerializers
from customer.utils import fetch_user_and_vendor, client_is_owner
# Get logger for application
application_logger = logging.getLogger('application')




class CustomerProfileView(generics.RetrieveAPIView):
    """
       API endpoint for clients to retrieve their profile settings.
        *   *URL:* /api/client/settings/<str:pid>/
        *   *Method:* GET
        *   *Authentication:* Requires a valid authentication token in the Authorization header.
         *   *Response (JSON):*
                *   On success (HTTP 200 OK for GET):
                        json
                         {
                            "id": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                            "user": {
                               "id": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                                "email": "client@outlook.com",
                                "full_name": "DANIEL OKORIE EZICHI",
                                 "phone": "08033333333",
                                  "role": "client"
                             },
                            "phone": "08011111111",
                             "address": "Some Location",
                            "city": "Some city",
                            "state": "Some state",
                             "country": "Some Country",
                             "image": "/media/uploads/image_profile.png"
                           }
                       
                *   On failure (HTTP 400, 404 or 500):
                     json
                     {
                         "error": "Error message" // Error message explaining the failure
                     }
                   Possible Error Messages:
                   * "You do not have permission to perform this action.": If the user is not a client
                   *  "Profile not found": If profile with pid is not found.
                   * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    queryset =  Profile.objects.all()
    serializer_class =  ProfileSerializers
    permission_classes = (IsAuthenticated, )
    lookup_field = 'pid'

    def retrieve(self, request, *args, **kwargs):
        """
        Returns a single serialized instance of the profile data, on successful user authentication
        """
        user = self.request.user
        try:
            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
            if error_response:
                application_logger.error(f"Error fetching user or profile: {error_response}")
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)
           
            if user_obj.role == 'client':
                try:
                    profile = Profile.objects.get(pid=self.kwargs['pid'])
                    client_is_owner(user_obj, obj=profile)
                    serializer = self.get_serializer(profile)
                    application_logger.info(f"Successfully retrieved profile with pid {self.kwargs['pid']} for user {user.email}")
                    return Response(serializer.data, status=status.HTTP_200_OK)
                except Profile.DoesNotExist:
                    application_logger.error(f"Profile with pid {self.kwargs['pid']} not found for client {user.email}")
                    raise NotFound("Profile not found")
        
            else:
                application_logger.error(f"User with email: {user.email} is not a client. Profile not found")
                return Response(
                    {'error': f'You do not have permission to perform this action.',
                    'Reason' : f'{user.email} is not a client. Profile not found.'
                    }, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            application_logger.error(f"Permission denied: {e} for user {user.email}")
            return Response(
            {'error': f'You do not have permission to perform this action.',
            'Reason' : f'{user.email} is not the owner of This Object'
            }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while retrieving profile settings with id {self.kwargs['pid']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)







class CustomerProfileUpdateView(generics.RetrieveUpdateAPIView):
    """
        API endpoint for clients to retrieve and update their profile settings.
         *   *URL:* /api/client/settings/update/<str:pid>/
        *   *Method:*  PUT
        *   *Authentication:* Requires a valid authentication token in the Authorization header for PUT requests.
          *   *Request Body (JSON for PUT):*
                json
                 {
                    "phone": "08011111111",  // Client's phone number
                    "address": "Some Location",   // Client's address
                    "city": "Some city", //Client's city
                    "state": "Some state", //Client's state
                    "country": "Some Country", //Client's country
                      "image": "/media/uploads/shop_image.png" //Client's profile image
                 }
          *   *Response (JSON):*
                 *   On success (HTTP 200 OK for PUT):
                        json
                         {
                            "id": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                            "user": {
                               "id": "b8b873bb-22b9-47f5-b0be-68668d077d60",
                                "email": "client@outlook.com",
                                "full_name": "DANIEL OKORIE EZICHI",
                                 "phone": "08033333333",
                                  "role": "client"
                             },
                            "phone": "08011111111",
                             "address": "Some Location",
                            "city": "Some city",
                            "state": "Some state",
                             "country": "Some Country",
                              "image": "/media/uploads/image_profile.png"
                           }
                       
                *   On failure (HTTP 400, 404 or 500):
                     json
                     {
                         "error": "Error message" // Error message explaining the failure
                     }
                     
                  Possible error messages:
                    * "You do not have permission to perform this action.": If the user is not a client
                    *  "Profile not found": If profile with pid is not found.
                   * "An error occurred, please check your input or contact support. {e}": if any error occurs during the request process.
    """
    queryset =  Profile.objects.all()
    serializer_class =  ProfileSerializers
    permission_classes = (IsAuthenticated, )
    parser_classes = (MultiPartParser, FormParser) # Add parser classes for handling file uploads
    lookup_field = 'pid'


    def update(self, request, *args, **kwargs):
        """
        Updates the profile object and returns the serialized data or an error if any error occurs
        """
        user = self.request.user
        try:
            user_obj, vendor_obj, error_response = fetch_user_and_vendor(user)
            if error_response:
                application_logger.error(f"Error fetching user or profile: {error_response}")
                return Response({'error': error_response}, status=status.HTTP_404_NOT_FOUND)
           
            if user_obj.role == 'client':
                try:
                  profile = Profile.objects.get(user=user_obj, pid=self.kwargs['pid'])
                  client_is_owner(user_obj, obj=profile)
                  serializer = self.get_serializer(profile, data=request.data, partial=True)
                  serializer.is_valid(raise_exception=True)
                  self.perform_update(serializer)
                  application_logger.info(f"Profile with id {profile.id} updated by user {request.user.email}")
                  return Response(serializer.data, status=status.HTTP_200_OK)
                except Profile.DoesNotExist:
                  application_logger.error(f"Profile with pid {self.kwargs['pid']} not found for client {user.email}")
                  raise NotFound("Profile not found")
            else:
                application_logger.error(f"User with email: {user.email} is not a client. Profile not found")
                return Response(
                    {'error': f'You do not have permission to perform this action.',
                    'Reason' : f'{user.email} is not a client. Profile not found.'
                    }, status=status.HTTP_400_BAD_REQUEST)
        except PermissionDenied as e:
            application_logger.error(f"Permission denied: {e} for user {user.email} while updating profile with id {self.kwargs['pid']}")
            return Response(
                {'error': f'You do not have permission to perform this action.',
                'Reason' : f'{user.email} is not the owner of This Object '
                }, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            application_logger.error(f"An unexpected error occurred while updating profile settings with id {self.kwargs['pid']}, {e}")
            return Response({'error': f'An error occurred: {e}'}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)













































