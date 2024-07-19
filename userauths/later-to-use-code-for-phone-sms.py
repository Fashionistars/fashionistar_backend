# # utils.py
# from twilio.rest import Client
# from django.conf import settings

# def send_sms(to, body):
#     client = Client(settings.TWILIO_ACCOUNT_SID, settings.TWILIO_AUTH_TOKEN)
#     message = client.messages.create(
#         body=body,
#         from_=settings.TWILIO_PHONE_NUMBER,
#         to=to
#     )
#     return message.sid


# from django.core.mail import EmailMultiAlternatives
# from django.shortcuts import get_object_or_404
# from django.core.exceptions import ObjectDoesNotExist
# from rest_framework.exceptions import NotFound, APIException
# from django.template.loader import render_to_string
# from django.conf import settings
# from django.db.models import Q

# # Rest framework
# from rest_framework.views import APIView
# from rest_framework import status, viewsets, generics
# from rest_framework.decorators import api_view, action
# from rest_framework.response import Response
# from rest_framework_simplejwt.views import TokenObtainPairView
# from rest_framework.permissions import AllowAny, IsAuthenticated
# from rest_framework_simplejwt.tokens import RefreshToken
# from rest_framework.exceptions import AuthenticationFailed
# from rest_framework import serializers

# # Others
# import json
# import random
# import time
# import datetime

# # Models
# from userauths.models import Profile, User, Tokens

# # Serializers
# from userauths.serializer import RegisterSerializer, MyTokenObtainPairSerializer

# # Utils
# from userauths.utils import EmailManager, generate_token, send_sms

# # Hashing
# from cryptography.fernet import Fernet
# import base64

# # Swagger
# from drf_yasg.utils import swagger_auto_schema
# from drf_yasg import openapi

# # Ensure that the key is 32 bytes by padding or truncating
# base_key = settings.SECRET_KEY.encode().ljust(32, b'\0')[:32]
# cipher_suite = Fernet(base64.urlsafe_b64encode(base_key))

# class MyTokenObtainPairView(TokenObtainPairView):
#     serializer_class = MyTokenObtainPairSerializer

# class RegisterView(generics.CreateAPIView):
#     """
#     Registration of new user using either email or phone number for signing up.
#     Args:
#         email: Input field of the user based on user's choice.
#         phone_number: Input field for phone number.
#         password: Password and password2 (Check the serializers.py to see the implementation).
#     """
#     queryset = User.objects.all()
#     permission_classes = (AllowAny,)
#     serializer_class = RegisterSerializer

#     def create(self, request, *args, **kwargs):
#         """OTP verification and validation"""
#         token = generate_token()
#         email = request.data.get('email')
#         phone = request.data.get('phone')

#         serializer = RegisterSerializer(data=request.data)
#         try:
#             if phone:
#                 if User.objects.filter(phone=phone).exists():
#                     return Response({"message": "Phone number already in use"}, status=status.HTTP_400_BAD_REQUEST)

#                 user_data = {
#                     'phone': phone,
#                     'password': request.data.get('password'),
#                     'role': request.data.get('role')
#                 }
#                 # Save the user data
#                 user_instance = User.objects.create_user(**user_data)

#                 # Send OTP to the phone
#                 send_sms(to=phone, body=f"Your OTP is: {token}")

#                 # Save the token
#                 encrypted_token = cipher_suite.encrypt(token.encode()).decode()
#                 new_token = Tokens()
#                 new_token.phone = phone
#                 new_token.action = 'register'
#                 new_token.token = encrypted_token
#                 new_token.exp_date = time.time() + 300
#                 new_token.save()

#                 return Response({"message": "Saved to database and OTP sent to phone"}, status=status.HTTP_201_CREATED)
#             else:
#                 if User.objects.filter(email=email).exists():
#                     return Response({"message": "Email already in use"}, status=status.HTTP_400_BAD_REQUEST)

#                 user_data = {
#                     'email': email,
#                     'password': request.data.get('password'),
#                     'role': request.data.get('role')
#                 }
#                 user_instance = User.objects.create_user(**user_data)
#                 serializer.is_valid(raise_exception=True)
#                 user_instance = serializer.save()
#                 res_data = serializer.data
#                 timestamp = time.time() + 300
#                 dt_object = datetime.datetime.fromtimestamp(timestamp)

#                 EmailManager.send_mail(
#                     subject="Fashionistar",
#                     recipients=[user_instance.email],
#                     template_name="otp.html",
#                     context={"user": user_instance.id, "token": token, "time": dt_object}
#                 )

#                 encrypted_token = cipher_suite.encrypt(token.encode()).decode()

#                 new_token = Tokens()
#                 new_token.email = user_instance.email
#                 new_token.action = 'register'
#                 new_token.token = encrypted_token
#                 new_token.exp_date = time.time() + 300
#                 new_token.save()

#                 res = {"message": "Token sent!", "code": 200, "data": res_data}
#                 return Response(res, status=status.HTTP_200_OK)

#         except serializers.ValidationError as error:
#             return Response({"message": f"Validation error: {str(error)}"}, status=status.HTTP_400_BAD_REQUEST)
#         except Exception as e:
#             return Response({"message": f"An error occurred: {str(e)}"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)





# TWILIO_ACCOUNT_SID = 'your_account_sid'
# TWILIO_AUTH_TOKEN = 'your_auth_token'
# TWILIO_PHONE_NUMBER = 'your_twilio_phone_number'


# pip install twilio




