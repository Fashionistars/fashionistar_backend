"""
Serializers برای API های Analytics
"""
from rest_framework import serializers
from .models import Metric, UserActivity, PerformanceMetric, BusinessMetric, AlertRule, Alert


class MetricSerializer(serializers.ModelSerializer):
    """
    Serializer برای مدل Metric
    """
    
    class Meta:
        model = Metric
        fields = [
            'id', 'name', 'metric_type', 'value', 
            'tags', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp']


class UserActivitySerializer(serializers.ModelSerializer):
    """
    Serializer برای مدل UserActivity
    """
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = UserActivity
        fields = [
            'id', 'user', 'user_username', 'action', 'resource', 
            'resource_id', 'ip_address', 'user_agent', 'session_id',
            'metadata', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp', 'user_username']


class PerformanceMetricSerializer(serializers.ModelSerializer):
    """
    Serializer برای مدل PerformanceMetric
    """
    user_username = serializers.CharField(source='user.username', read_only=True)
    
    class Meta:
        model = PerformanceMetric
        fields = [
            'id', 'endpoint', 'method', 'response_time_ms', 
            'status_code', 'user', 'user_username', 'error_message',
            'metadata', 'timestamp'
        ]
        read_only_fields = ['id', 'timestamp', 'user_username']


class BusinessMetricSerializer(serializers.ModelSerializer):
    """
    Serializer برای مدل BusinessMetric
    """
    
    class Meta:
        model = BusinessMetric
        fields = [
            'id', 'metric_name', 'value', 'period_start', 
            'period_end', 'metadata', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']


class AlertRuleSerializer(serializers.ModelSerializer):
    """
    Serializer برای مدل AlertRule
    """
    
    class Meta:
        model = AlertRule
        fields = [
            'id', 'name', 'metric_name', 'operator', 'threshold',
            'severity', 'is_active', 'description', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at']


class AlertSerializer(serializers.ModelSerializer):
    """
    Serializer برای مدل Alert
    """
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
    """
    Serializer برای ثبت متریک جدید
    """
    name = serializers.CharField(max_length=255)
    value = serializers.FloatField()
    metric_type = serializers.ChoiceField(
        choices=['counter', 'gauge', 'histogram', 'timer'],
        default='gauge'
    )
    tags = serializers.JSONField(required=False, default=dict)


class UserAnalyticsQuerySerializer(serializers.Serializer):
    """
    Serializer برای پارامترهای جستجوی تحلیل‌های کاربر
    """
    user_id = serializers.IntegerField(required=False)
    days = serializers.IntegerField(default=30, min_value=1, max_value=365)


class PerformanceAnalyticsQuerySerializer(serializers.Serializer):
    """
    Serializer برای پارامترهای جستجوی تحلیل‌های عملکرد
    """
    days = serializers.IntegerField(default=7, min_value=1, max_value=90)


class BusinessMetricsQuerySerializer(serializers.Serializer):
    """
    Serializer برای پارامترهای جستجوی متریک‌های کسب و کار
    """
    period_start = serializers.DateTimeField()
    period_end = serializers.DateTimeField()
    
    def validate(self, data):
        """
        اعتبارسنجی محدوده زمانی
        """
        if data['period_start'] >= data['period_end']:
            raise serializers.ValidationError(
                "زمان شروع باید قبل از زمان پایان باشد"
            )
        return data