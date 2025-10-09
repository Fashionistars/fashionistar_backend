from rest_framework import serializers
from rest_framework import generics, status
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated

from vendor.models import Vendor

class SetTransactionPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=4, min_length=4, write_only=True)
    confirm_password = serializers.CharField(max_length=4, min_length=4, write_only=True)

    def validate(self, data):
        if data['password'] != data['confirm_password']:
            raise serializers.ValidationError("Passwords do not match.")
        return data

    def save(self, user):
        vendor = Vendor.objects.get(user=user)
        vendor.set_transaction_password(self.validated_data['password'])


class ValidateTransactionPasswordSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=4, min_length=4, write_only=True)





class SetTransactionPasswordView(generics.GenericAPIView):
    serializer_class = SetTransactionPasswordSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        serializer.save(user=request.user)
        return Response({"message": "Transaction password set successfully."}, status=status.HTTP_200_OK)



class ValidateTransactionPasswordView(generics.GenericAPIView):
    serializer_class = ValidateTransactionPasswordSerializer
    permission_classes = (IsAuthenticated,)

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vendor = Vendor.objects.get(user=request.user)
        if vendor.check_transaction_password(serializer.validated_data['password']):
            return Response({"message": "Password validated successfully."}, status=status.HTTP_200_OK)
        return Response({"message": "Invalid transaction password."}, status=status.HTTP_400_BAD_REQUEST)


