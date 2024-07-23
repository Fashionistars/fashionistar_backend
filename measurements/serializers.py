from rest_framework import serializers
from .models import Measurement

class GenerateAccessCodeSerializer(serializers.Serializer):
    email = serializers.EmailField()
    full_name = serializers.CharField(max_length=1000)
    phone = serializers.CharField(max_length=20)
    gender = serializers.ChoiceField(choices=['M', 'F', 'O'])

class FetchMeasurementSerializer(serializers.Serializer):
    access_code = serializers.CharField(max_length=100)
