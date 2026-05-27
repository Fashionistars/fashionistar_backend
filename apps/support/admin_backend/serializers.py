# apps/support/admin_backend/serializers.py
from rest_framework import serializers

class AdminAssignTicketSerializer(serializers.Serializer):
    assignee_id = serializers.UUIDField()

class AdminResolveTicketSerializer(serializers.Serializer):
    notes = serializers.CharField(max_length=2000)
