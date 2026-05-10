# from rest_framework import serializers

# # Serializer for handling the deposit amount
# class DepositAmountSerializer(serializers.Serializer):
#     amount = serializers.DecimalField(max_digits=10, decimal_places=2, min_value=0.01)



from rest_framework import serializers

class DepositAmountSerializer(serializers.Serializer):
    amount = serializers.DecimalField(max_digits=10, decimal_places=2, required=True)
