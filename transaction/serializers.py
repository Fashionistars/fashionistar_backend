from django.shortcuts import render
from rest_framework import serializers


class PaymentSerializer(serializers.Serializer):
    preauthorize = serializers.BooleanField()
    usesecureauth = serializers.BooleanField()
    card_number = serializers.CharField(max_length=16)
    cvv = serializers.CharField(max_length=4)
    expiry_month = serializers.CharField(max_length=2)
    expiry_year = serializers.CharField(max_length=2)
    currency = serializers.CharField(max_length=3)
    amount = serializers.CharField(max_length=10)
    email = serializers.EmailField()
    fullname = serializers.CharField(max_length=100)
    # tx_ref = serializers.CharField(max_length=50)
    # redirect_url = serializers.URLField()
    
    
