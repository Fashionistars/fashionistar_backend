"""
Analytics Serializers for Fashionistar.
"""

from rest_framework import serializers
from .models import Metric, UserActivity, PerformanceMetric, BusinessMetric, AlertRule, Alert


class MetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = Metric
        fields = [
            'id', 'name', 'metric_type', 'value', 
            'tags', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp']


class UserActivitySerializer(serializers.ModelSerializer):
    user_username = serializers.SerializerMethodField()
    
    class Meta:
        model = UserActivity
        fields = [
            'id', 'user', 'user_username', 'action', 'resource', 
            'resource_id', 'ip_address', 'user_agent', 'session_id',
            'metadata', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp', 'user_username']
        
    def get_user_username(self, obj) -> str:
        if obj.user:
            return obj.user.phone or obj.user.email or str(obj.user.id)
        return ''


class PerformanceMetricSerializer(serializers.ModelSerializer):
    user_username = serializers.SerializerMethodField()
    
    class Meta:
        model = PerformanceMetric
        fields = [
            'id', 'endpoint', 'method', 'response_time_ms', 
            'status_code', 'user', 'user_username', 'error_message',
            'metadata', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp', 'user_username']

    def get_user_username(self, obj) -> str:
        if obj.user:
            return obj.user.phone or obj.user.email or str(obj.user.id)
        return ''


class BusinessMetricSerializer(serializers.ModelSerializer):
    class Meta:
        model = BusinessMetric
        fields = [
            'id', 'metric_name', 'value', 'period_start', 
            'period_end', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AlertRuleSerializer(serializers.ModelSerializer):
    class Meta:
        model = AlertRule
        fields = [
            'id', 'name', 'metric_name', 'operator', 'threshold',
            'severity', 'is_active', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AlertSerializer(serializers.ModelSerializer):
    rule_name = serializers.CharField(source='rule.name', read_only=True)
    rule_severity = serializers.CharField(source='rule.severity', read_only=True)
    
    class Meta:
        model = Alert
        fields = [
            'id', 'rule', 'rule_name', 'rule_severity', 'status',
            'metric_value', 'message', 'metadata', 'fired_at', 'resolved_at'
        ]
        read_only_fields = ['id', 'fired_at', 'rule_name', 'rule_severity']


class RecordMetricSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=255)
    value = serializers.FloatField()
    metric_type = serializers.ChoiceField(
        choices=['counter', 'gauge', 'histogram', 'timer'],
        default='gauge'
    )
    tags = serializers.JSONField(required=False, default=dict)


class UserAnalyticsQuerySerializer(serializers.Serializer):
    user_id = serializers.IntegerField(required=False)
    days = serializers.IntegerField(default=30, min_value=1, max_value=365)


class PerformanceAnalyticsQuerySerializer(serializers.Serializer):
    days = serializers.IntegerField(default=7, min_value=1, max_value=90)


class BusinessMetricsQuerySerializer(serializers.Serializer):
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    
    def validate(self, data):
        if data['period_start'] >= data['period_end']:
            raise serializers.ValidationError("Period start must be before period end.")
        return data