"""
Serializers برای اپلیکیشن DevOps
"""
from rest_framework import serializers
from django.contrib.auth.models import User
from .models import (
    EnvironmentConfig,
    SecretConfig,
    DeploymentHistory,
    HealthCheck,
    ServiceMonitoring
)


class EnvironmentConfigSerializer(serializers.ModelSerializer):
    """Serializer برای تنظیمات محیط"""
    
    secrets_count = serializers.SerializerMethodField()
    deployments_count = serializers.SerializerMethodField()
    
    class Meta:
        model = EnvironmentConfig
        fields = [
            'id', 'name', 'environment_type', 'description', 'is_active',
            'created_at', 'updated_at', 'created_by', 'secrets_count', 'deployments_count'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'secrets_count', 'deployments_count']
    
    def get_secrets_count(self, obj):
        """تعداد secrets فعال"""
        return obj.secrets.filter(is_active=True).count()
    
    def get_deployments_count(self, obj):
        """تعداد کل deployment ها"""
        return obj.deployments.count()


class SecretConfigSerializer(serializers.ModelSerializer):
    """Serializer برای تنظیمات محرمانه"""
    
    is_expired = serializers.SerializerMethodField()
    days_until_expiry = serializers.SerializerMethodField()
    
    class Meta:
        model = SecretConfig
        fields = [
            'id', 'environment', 'key_name', 'encrypted_value', 'category',
            'description', 'is_active', 'expires_at', 'created_at', 'updated_at',
            'created_by', 'is_expired', 'days_until_expiry'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'is_expired', 'days_until_expiry']
        extra_kwargs = {
            'encrypted_value': {'write_only': True}  # برای امنیت، مقدار رمزنگاری شده نمایش داده نمی‌شود
        }
    
    def get_is_expired(self, obj):
        """بررسی انقضا"""
        return obj.is_expired
    
    def get_days_until_expiry(self, obj):
        """روزهای باقی‌مانده تا انقضا"""
        if obj.expires_at:
            from django.utils import timezone
            delta = obj.expires_at - timezone.now()
            return delta.days if delta.days > 0 else 0
        return None
    
    def to_representation(self, instance):
        """سفارشی‌سازی نمایش"""
        data = super().to_representation(instance)
        # نمایش نام محیط به جای ID
        data['environment_name'] = instance.environment.name
        return data


class DeploymentHistorySerializer(serializers.ModelSerializer):
    """Serializer برای تاریخچه deployment"""
    
    environment_name = serializers.CharField(source='environment.name', read_only=True)
    deployed_by_username = serializers.CharField(source='deployed_by.username', read_only=True)
    duration_seconds = serializers.SerializerMethodField()
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    rollback_from_version = serializers.CharField(source='rollback_from.version', read_only=True)
    
    class Meta:
        model = DeploymentHistory
        fields = [
            'id', 'environment', 'environment_name', 'version', 'commit_hash',
            'branch', 'status', 'status_display', 'started_at', 'completed_at',
            'deployed_by', 'deployed_by_username', 'deployment_logs',
            'rollback_from', 'rollback_from_version', 'artifacts_url',
            'duration_seconds'
        ]
        read_only_fields = [
            'id', 'started_at', 'completed_at', 'environment_name',
            'deployed_by_username', 'status_display', 'rollback_from_version',
            'duration_seconds'
        ]
    
    def get_duration_seconds(self, obj):
        """مدت زمان deployment به ثانیه"""
        if obj.duration:
            return int(obj.duration.total_seconds())
        return None


class HealthCheckSerializer(serializers.ModelSerializer):
    """Serializer برای نتایج health check"""
    
    environment_name = serializers.CharField(source='environment.name', read_only=True)
    status_display = serializers.CharField(source='get_status_display', read_only=True)
    time_ago = serializers.SerializerMethodField()
    
    class Meta:
        model = HealthCheck
        fields = [
            'id', 'environment', 'environment_name', 'service_name',
            'endpoint_url', 'status', 'status_display', 'response_time',
            'status_code', 'response_data', 'error_message', 'checked_at',
            'time_ago'
        ]
        read_only_fields = ['id', 'environment_name', 'status_display', 'time_ago']
    
    def get_time_ago(self, obj):
        """زمان گذشته از آخرین بررسی"""
        from django.utils import timezone
        delta = timezone.now() - obj.checked_at
        
        if delta.days > 0:
            return f"{delta.days} روز پیش"
        elif delta.seconds > 3600:
            hours = delta.seconds // 3600
            return f"{hours} ساعت پیش"
        elif delta.seconds > 60:
            minutes = delta.seconds // 60
            return f"{minutes} دقیقه پیش"
        else:
            return "اکنون"


class ServiceMonitoringSerializer(serializers.ModelSerializer):
    """Serializer برای مانیتورینگ سرویس‌ها"""
    
    environment_name = serializers.CharField(source='environment.name', read_only=True)
    service_type_display = serializers.CharField(source='get_service_type_display', read_only=True)
    last_check = serializers.SerializerMethodField()
    uptime_24h = serializers.SerializerMethodField()
    
    class Meta:
        model = ServiceMonitoring
        fields = [
            'id', 'environment', 'environment_name', 'service_name',
            'service_type', 'service_type_display', 'health_check_url',
            'check_interval', 'timeout', 'is_active', 'alert_on_failure',
            'created_at', 'updated_at', 'last_check', 'uptime_24h'
        ]
        read_only_fields = [
            'id', 'created_at', 'updated_at', 'environment_name',
            'service_type_display', 'last_check', 'uptime_24h'
        ]
    
    def get_last_check(self, obj):
        """آخرین نتیجه health check"""
        latest_check = obj.environment.health_checks.filter(
            service_name=obj.service_name
        ).first()
        
        if latest_check:
            return {
                'status': latest_check.status,
                'status_display': latest_check.get_status_display(),
                'response_time': latest_check.response_time,
                'checked_at': latest_check.checked_at,
                'error_message': latest_check.error_message
            }
        return None
    
    def get_uptime_24h(self, obj):
        """uptime در 24 ساعت گذشته"""
        from django.utils import timezone
        from django.db.models import Count
        
        from_time = timezone.now() - timezone.timedelta(hours=24)
        
        total_checks = obj.environment.health_checks.filter(
            service_name=obj.service_name,
            checked_at__gte=from_time
        ).count()
        
        if total_checks == 0:
            return None
        
        healthy_checks = obj.environment.health_checks.filter(
            service_name=obj.service_name,
            checked_at__gte=from_time,
            status='healthy'
        ).count()
        
        uptime_percent = (healthy_checks / total_checks) * 100
        
        return {
            'uptime_percent': round(uptime_percent, 2),
            'total_checks': total_checks,
            'healthy_checks': healthy_checks
        }


class DeploymentRequestSerializer(serializers.Serializer):
    """Serializer برای درخواست deployment"""
    
    environment = serializers.CharField(max_length=100)
    version = serializers.CharField(max_length=50)
    branch = serializers.CharField(max_length=100, default='main')
    build_images = serializers.BooleanField(default=True)
    run_migrations = serializers.BooleanField(default=True)
    restart_services = serializers.BooleanField(default=True)
    
    def validate_environment(self, value):
        """اعتبارسنجی محیط"""
        try:
            EnvironmentConfig.objects.get(name=value, is_active=True)
            return value
        except EnvironmentConfig.DoesNotExist:
            raise serializers.ValidationError(f"محیط {value} یافت نشد یا غیرفعال است")


class RollbackRequestSerializer(serializers.Serializer):
    """Serializer برای درخواست rollback"""
    
    environment = serializers.CharField(max_length=100)
    target_deployment_id = serializers.UUIDField()
    
    def validate(self, data):
        """اعتبارسنجی کامل"""
        try:
            environment = EnvironmentConfig.objects.get(
                name=data['environment'],
                is_active=True
            )
        except EnvironmentConfig.DoesNotExist:
            raise serializers.ValidationError(f"محیط {data['environment']} یافت نشد")
        
        try:
            DeploymentHistory.objects.get(
                id=data['target_deployment_id'],
                environment=environment,
                status='success'
            )
        except DeploymentHistory.DoesNotExist:
            raise serializers.ValidationError("Deployment مقصد یافت نشد یا موفق نبوده")
        
        return data


class ContainerActionSerializer(serializers.Serializer):
    """Serializer برای عملیات container"""
    
    ACTION_CHOICES = [
        ('start', 'شروع'),
        ('stop', 'توقف'),
        ('restart', 'راه‌اندازی مجدد'),
    ]
    
    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    container_name = serializers.CharField(max_length=100)


class ComposeActionSerializer(serializers.Serializer):
    """Serializer برای عملیات Docker Compose"""
    
    ACTION_CHOICES = [
        ('start', 'شروع'),
        ('stop', 'توقف'),
        ('restart', 'راه‌اندازی مجدد'),
        ('build', 'ساخت'),
        ('pull', 'دانلود'),
    ]
    
    action = serializers.ChoiceField(choices=ACTION_CHOICES)
    services = serializers.ListField(
        child=serializers.CharField(max_length=100),
        required=False,
        allow_empty=True
    )
    no_cache = serializers.BooleanField(default=False, required=False)