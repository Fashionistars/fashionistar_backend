# apps/chat/admin_backend/serializers.py
from rest_framework import serializers

class AdminResolveEscalationSerializer(serializers.Serializer):
    notes = serializers.CharField(max_length=1000)
    resolution_status = serializers.ChoiceField(choices=[("resolved", "Resolved"), ("dismissed", "Dismissed")])
