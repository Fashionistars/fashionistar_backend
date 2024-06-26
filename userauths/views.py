from django.core.mail import EmailMultiAlternatives
from django.shortcuts import get_object_or_404
from django.core.exceptions import ObjectDoesNotExist
from rest_framework.exceptions import NotFound, APIException
from django.template.loader import render_to_string
from django.conf import settings
from django.db.models import Q

# Restframework
from rest_framework.views import APIView
from rest_framework import status, viewsets, generics
from rest_framework.decorators import api_view, action
from rest_framework.response import Response
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework import generics
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.decorators import api_view, permission_classes
from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework.exceptions import AuthenticationFailed

# Others
import json
import random
import time
import datetime
# Models
from userauths.models import Profile, User, Tokens

# Serializers
from userauths.serializer import *

# utils
from userauths.utils import EmailManager, generate_token

# Hashing
from django.conf import settings
from cryptography.fernet import Fernet
import base64

# Swagger
from drf_yasg.utils import swagger_auto_schema
from drf_yasg import openapi

base_key = settings.SECRET_KEY.encode()

# Ensure that the key is 32 bytes by padding or truncating
base_key = base_key.ljust(32, b'\0')[:32]

# Encode the key in URL-safe base64 format
cipher_suite = Fernet(base64.urlsafe_b64encode(base_key))


class MyTokenObtainPairView(TokenObtainPairView):
    serializer_class = MyTokenObtainPairSerializer


class RegisterView(generics.CreateAPIView):
    """
    Registeration of new user using either email or phone number for signing up
        Args:
        email: Input field of the user base on user's choice
        phone_number: Input field for phone number
        password: password and password2(Check the serializers.py to see the implementation)
    """
    queryset = User.objects.all()
    permission_classes = (AllowAny,)
    serializer_class = RegisterSerializer

    def create(self, request, *args, **kwargs):
        """OTP verification and validation"""
        token = generate_token()
        email = request.data.get('email')
        phone = request.data.get('phone')

        serializer = RegisterSerializer(data=request.data)
        print(request.data)
        try:
            if phone:
                user_data = {
                    'phone': phone,
                    'password': request.data.get('password'),
                    'role': request.data.get('role')
                }
                print(user_data)
                return Response({"message": "Saved to database"}, status=status.HTTP_202_ACCEPTED)
            else:
                serializer.is_valid(raise_exception=True)
                user_instance = serializer.save()
                res_data = serializer.data
                timestamp = time.time() + 300
                dt_object = datetime.datetime.fromtimestamp(timestamp)
                dt_object += datetime.timedelta()
                
                EmailManager.send_mail(
                    subject="Fashionistar",
                    recipients=[user_instance.email],
                    template_name="otp.html",
                    context={"user": user_instance.id, "token": token, "time": dt_object}
                )

                encrypted_token = cipher_suite.encrypt(token.encode()).decode()
                
                new_token = Tokens()
                new_token.email = user_instance.email
                new_token.action = 'register'
                new_token.token = encrypted_token
                new_token.exp_date = time.time() + 300
                new_token.save()
                
                res = {"message": "Token sent!", "code": 200, "data": res_data}
                return Response(res, status=status.HTTP_200_OK)
                
        except serializers.ValidationError as error:
            return Response({"mesage": "Still error " + str(error)}, status=status.HTTP_400_BAD_REQUEST)
            


class VerifyUserViewSet(viewsets.ViewSet):
    """
    Perform email verification and phone number verification
    for registration
    """
    permission_classes = []
    @swagger_auto_schema(
        request_body=VerifyUserSerializer,
        responses={200: 'Success', 400: 'Bad Request'},
        operation_description="Verify user with valid email upon signing up"
    )
    @action(detail=False, methods=['post'])
    def verify_user(self, request):
        """
        Email verification: Send 4 digits OTP to user email.
        Phone number verification: Send 4 digits OTP to user valid phone number.(Coming soon!!!)
        """
        serializer = VerifyUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        otp = serializer.validated_data['otp']
        
        token = Tokens.objects.filter(Q(action='register')).order_by('-created_at')[:1].first()
        key = token.token
        decrypted_key = cipher_suite.decrypt(key.encode()).decode()
        
        if decrypted_key == otp and token.exp_date >= time.time():
            email = token.email
            user = User.objects.get(email=email)
            token.date_used = datetime.datetime.now()
            token.used = True
            user.verified = True
            user.is_active = True
            user.save()
            token.save()
            return Response({"message": "User successfully verified"}, status=status.HTTP_200_OK)
        else:
            return Response({"error": "Invalid or expired OTP"})





class LoginView(TokenObtainPairView):
    serializer_class = LoginSerializer
    permission_classes = ()
    
    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        
        email = serializer.initial_data['email']
        # phone_number = serializer.initial_data['phone_number']
            
        password = serializer.initial_data['password']

        try:
            user = User.objects.get(email=email)
            if not user.check_password(password):
                raise AuthenticationFailed("Invalid authentication credentials")
            
            if not user.is_active:
                raise AuthenticationFailed("Your account is not active.")
        
        except User.DoesNotExist:
            raise AuthenticationFailed("Invalid authentication credentials")
        
        if serializer.is_valid():
            
            if serializer.is_valid():
                tokens = serializer.validated_data
                custom_data = {
                    'access': str(tokens['access']),
                    'refresh': str(tokens['refresh']),
                    'user_id': user.id,
                }
                return Response(custom_data, status=status.HTTP_201_CREATED)
        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)
    

class LogoutView(APIView):
    """Logout functionality"""
    permission_classes = (IsAuthenticated,)

    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        refresh_token = serializer.validated_data['refresh_token']
        try:
            token = RefreshToken(refresh_token)
            token.blacklist()
            return Response(status=status.HTTP_205_RESET_CONTENT)
        except Exception as e:
            return Response(status=status.HTTP_400_BAD_REQUEST)
    
@api_view(['GET'])
def getRoutes(request):
    # It defines a list of API routes that can be accessed.
    routes = [
        '/api/token/',
        '/api/register/',
        '/api/token/refresh/',
        '/api/test/'
    ]
    # It returns a DRF Response object containing the list of routes.
    return Response(routes)


@api_view(['GET', 'POST'])
@permission_classes([IsAuthenticated])
def testEndPoint(request):
    if request.method == 'GET':
        data = f"Congratulations {request.user}, your API just responded to a GET request."
        return Response({'response': data}, status=status.HTTP_200_OK)
    elif request.method == 'POST':
        try:
            body = request.body.decode('utf-8')
            data = json.loads(body)
            if 'text' not in data:
                return Response("Invalid JSON data", status=status.HTTP_400_BAD_REQUEST)
            text = data.get('text')
            data = f'Congratulations, your API just responded to a POST request with text: {text}'
            return Response({'response': data}, status=status.HTTP_200_OK)
        except json.JSONDecodeError:
            return Response("Invalid JSON data", status=status.HTTP_400_BAD_REQUEST)
    return Response("Invalid JSON data", status=status.HTTP_400_BAD_REQUEST)



class ProfileView(generics.RetrieveUpdateAPIView):
    permission_classes = (AllowAny,)
    serializer_class = ProfileSerializer

    def get_object(self):
        pid = self.kwargs['pid']
        try:
            user = get_object_or_404(User, profile__pid=pid)
            profile = get_object_or_404(Profile, user=user)
            return profile
        except ObjectDoesNotExist as e:
            raise NotFound(f"Profile not found: {str(e)}")
        except Exception as e:
            raise APIException(f"An error occurred: {str(e)}")

def generate_numeric_otp(length=7):
        # Generate a random 7-digit OTP
        otp = ''.join([str(random.randint(0, 9)) for _ in range(length)])
        return otp

class PasswordEmailVerify(generics.RetrieveAPIView):
    permission_classes = (AllowAny,)
    serializer_class = UserSerializer
    
    def get_object(self):
        email = self.kwargs['email']
        user = User.objects.get(email=email)
        
        if user:
            user.otp = generate_numeric_otp()
            uidb64 = user.pk
            
            refresh = RefreshToken.for_user(user)
            reset_token = str(refresh.access_token)

            # Store the reset_token in the user model for later verification
            user.reset_token = reset_token
            user.save()

            link = f"http://localhost:5173/create-new-password?otp={user.otp}&uidb64={uidb64}&reset_token={reset_token}"
            
            merge_data = {
                'link': link, 
                'username': user.username, 
            }
            subject = f"Password Reset Request"
            text_body = render_to_string("email/password_reset.txt", merge_data)
            html_body = render_to_string("email/password_reset.html", merge_data)
            
            msg = EmailMultiAlternatives(
                subject=subject, from_email=settings.FROM_EMAIL,
                to=[user.email], body=text_body
            )
            msg.attach_alternative(html_body, "text/html")
            msg.send()
        return user
    

class PasswordChangeView(generics.CreateAPIView):
    permission_classes = (AllowAny,)
    serializer_class = UserSerializer
    
    def create(self, request, *args, **kwargs):
        payload = request.data
        
        otp = payload['otp']
        uidb64 = payload['uidb64']
        reset_token = payload['reset_token']
        password = payload['password']

        print("otp ======", otp)
        print("uidb64 ======", uidb64)
        print("reset_token ======", reset_token)
        print("password ======", password)

        user = User.objects.get(id=uidb64, otp=otp)
        if user:
            user.set_password(password)
            user.otp = ""
            user.reset_token = ""
            user.save()

            
            return Response( {"message": "Password Changed Successfully"}, status=status.HTTP_201_CREATED)
        else:
            return Response( {"message": "An Error Occured"}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
