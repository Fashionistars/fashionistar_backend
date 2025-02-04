from rest_framework import serializers
from customer.models import DeliveryContact, ShippingAddress

# models
from userauths.models import User, Profile




class SetTransactionPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=4, min_length=4, write_only=True)
    confirm_password = serializers.CharField(max_length=4, min_length=4, write_only=True)

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def save(self, user):
        profile = Profile.objects.get(user=user)
        profile.set_transaction_password(self.validated_data['password'])


class ValidateTransactionPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=4, min_length=4, write_only=True)


class DeliveryContactSerializer(serializers.ModelSerializer):
    """
    Serializer for the DeliveryContact model.
    """
    class Meta:
        model = DeliveryContact
        fields = '__all__'

class ShippingAddressSerializer(serializers.ModelSerializer):
    """
    Serializer for the ShippingAddress model.
    """
    class Meta:
        model = ShippingAddress
        fields = '__all__'





class UserSerializer(serializers.ModelSerializer):
    """
    Serializer for the User model.
    """
    class Meta:
        model = User
        fields = ['id','email', 'full_name', 'phone', 'role']
        help_texts = {
            'id': 'The unique ID of the user.',
            'email': "The user's unique email address",
            'phone': "The user's phone number",
            'role': 'The role of this user, either "client" or "vendor"',
        }


class ProfileSerializer(serializers.ModelSerializer):
    """
    Serializer for the Profile model.
    """
    user = UserSerializer(help_text="User associated with the Profile.", read_only=True)
    deliveryContact = DeliveryContactSerializer(help_text="Delivery contact associated with this profile", read_only=True, allow_null=True)
    shippingAddress = ShippingAddressSerializer(help_text="Shipping address associated with this profile", read_only=True, allow_null=True)
    class Meta:
        model = Profile
        fields = '__all__'
        help_texts = {
            'id': 'The unique ID of the profile.',
            'user': 'The user associated with this profile.',
            'image': 'Profile image of the user',
            'full_name': 'The full name of the profile owner.',
            'about': 'Information about the profile.',
            'gender': 'The gender of the user, either "Male", "Female" or "Other"',
            'wallet_balance': 'The current wallet balance.',
            'transaction_password': 'The transaction password for the user.',
            'deliveryContact': 'Delivery contact information for the user.',
            'shippingAddress': 'Shipping address information for the user.',
             'country': 'The Country of the user',
             'city': 'The City of the user',
            'state': 'The state of the user',
            'address': 'The address of the user.',
            'newsletter': 'If user is subscribed to newsletter',
            'date': 'Date the user created an account',
             'pid': 'unique ID of the user',
             'qr_code': 'The Qr Code of the user',
            'mirrorsize_access_token': 'The token given by Mirrorsize',
            'measurement': 'measurement of the user if any',
            'paystack_recipient_code':'The paystack Recipient Code'

        }

    def to_representation(self, instance):
        """
        Overrides the default representation to include nested serializers for
        user, deliveryContact, and shippingAddress.
        """
        response = super().to_representation(instance)
        return response














