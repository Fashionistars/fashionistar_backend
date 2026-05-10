from rest_framework import serializers
from measurements.models import MeasurementVideo

class MeasurementVideoSerializer(serializers.ModelSerializer):
    class Meta:
        model = MeasurementVideo
        fields = ['id', 'user', 'video_url', 'created_at']
        read_only_fields = ['id', 'user', 'created_at']
