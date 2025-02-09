from userauths.models import Profile, User
from django.contrib.auth.password_validation import validate_password
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer
from rest_framework import serializers
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from rest_framework.decorators import parser_classes
from rest_framework.parsers import JSONParser

# ShippingAddress URLs and DeliveryContact URLs
from customer.serializers import DeliveryContactSerializer, ShippingAddressSerializer

User = get_user_model()
class MyTokenObtainPairSerializer(TokenObtainPairSerializer):
    '''
    class MyTokenObtainPairSerializer(TokenObtainPairSerializer):: This line creates a new token serializer called MyTokenObtainPairSerializer that is based on an existing one called TokenObtainPairSerializer. Think of it as customizing the way tokens work.
    @classmethod: This line indicates that the following function is a class method, which means it belongs to the class itself and not to an instance (object) of the class.
    def get_token(cls, user):: This is a function (or method) that gets called when we want to create a token for a user. The user is the person who's trying to access something on the website.
    token = super().get_token(user): Here, it's asking for a regular token from the original token serializer (the one it's based on). This regular token is like a key to enter the website.
    token['full_name'] = user.full_name, token['email'] = user.email, token['username'] = user.username: This code is customizing the token by adding extra information to it. For example, it's putting the user's full name, email, and username into the token. These are like special notes attached to the key.
    return token: Finally, the customized token is given back to the user. Now, when this token is used, it not only lets the user in but also carries their full name, email, and username as extra information, which the website can use as needed.
    '''
    @classmethod
    # Define a custom method to get the token for a user
    def get_token(cls, user):
        # Call the parent class's get_token method
        token = super().get_token(user)

        # Add custom claims to the token
        token['full_name'] = user.full_name
        token['email'] = user.email
        token['username'] = user.username
        try:
            token['vendor_id'] = user.vendor.id
        except:
            token['vendor_id'] = 0

        return token


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, required=True, validators=[validate_password])
    password2 = serializers.CharField(write_only=True, required=True)
    email = serializers.EmailField(required=False)
    phone = serializers.CharField(required=False)
    role = serializers.CharField(required=True)

    class Meta:
        model = User
        fields = ('email', 'phone', 'role', 'password', 'password2')

    def validate(self, attrs):
        if attrs['password'] != attrs['password2']:
            raise serializers.ValidationError({"password": "Password fields didn't match."})

        email = attrs.get('email')
        phone = attrs.get('phone')

        if email and phone:
            raise serializers.ValidationError("Either use email or phone number")
        
        if not email and not phone:
            raise serializers.ValidationError("Email or phone number is required.")

        if email and User.objects.filter(email=email).exists():
            raise serializers.ValidationError({"email": "This email has already been used."})

        if phone and User.objects.filter(phone=phone).exists():
            raise serializers.ValidationError({"phone": "This phone number has already been used."})

        return attrs

    def create(self, validated_data):
            email = validated_data.get('email')
            phone = validated_data.get('phone')
            password = validated_data.get('password')
            role = validated_data.get('role')
            user = User.objects.create_user(
                email=email,
                phone=phone,
                password=password,
                role=role
            )

            return user

    def to_representation(self, instance):
        """Convert the User instance to a JSON-serializable dictionary."""
        return {
            'id': instance.id,
            'email': instance.email,
            "phone": instance.phone,
            'role': instance.role
        }


class ResendTokenSerializer(serializers.Serializer):
    email = serializers.EmailField()

        
class VerifyUserSerializer(serializers.ModelSerializer):
    otp = serializers.CharField(write_only=True)
    
    class Meta:
        model = User
        fields = ['otp',]


@parser_classes([JSONParser])
class LoginSerializer(TokenObtainPairSerializer):
    email = serializers.EmailField(write_only=False, required=False)
    phone_number = serializers.CharField(required=False)
    password = serializers.CharField(required=True)
    default_error_messages = {
        'no_active_account': 'Your account is yet to be activated',
        'invalid_credentials': 'Invalid email or password'
    }

class LogoutSerializer(serializers.Serializer):
    refresh_token = serializers.CharField()


class UserSerializer(serializers.ModelSerializer):

    class Meta:
        model = User
        fields = '__all__'


class ProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = Profile
        fields = '__all__'

    def to_representation(self, instance):
        response = super().to_representation(instance)
        response['user'] = UserSerializer(instance.user).data
        response['deliveryContact'] = DeliveryContactSerializer(instance.deliveryContact).data if instance.deliveryContact else None
        response['shippingAddress'] = ShippingAddressSerializer(instance.shippingAddress).data if instance.shippingAddress else None
        return response


class PasswordResetSerializer(serializers.Serializer):
    email = serializers.EmailField()