from rest_framework import serializers
from apps.authentication.models import UnifiedUser

class UserSerializer(serializers.ModelSerializer):
    class Meta:
        model = UnifiedUser
        fields = ['id', 'email', 'phone', 'role', 'first_name', 'last_name', 'avatar', 'bio', 'country', 'city', 'state', 'address', 'auth_provider', 'is_verified', 'created_at']
        read_only_fields = ['id', 'role', 'auth_provider', 'is_verified', 'created_at']
