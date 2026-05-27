from rest_framework import serializers

class AdminProductRejectSerializer(serializers.Serializer):
    reason = serializers.CharField(max_length=500, required=True)

class AdminInventoryAdjustSerializer(serializers.Serializer):
    delta = serializers.IntegerField(required=True)
    reason = serializers.CharField(max_length=255, default="adjustment")
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")

