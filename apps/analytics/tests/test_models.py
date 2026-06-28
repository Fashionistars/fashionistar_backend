"""
تست‌های مربوط به models اپ Analytics
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from ..models import Metric, UserActivity, PerformanceMetric, BusinessMetric, AlertRule, Alert

User = get_user_model()


class MetricModelTest(TestCase):
    """
    تست‌های مربوط به مدل Metric
    """
    
    def test_metric_creation(self):
        """
        تست ایجاد متریک
        """
        metric = Metric.objects.create(
            name='test_metric',
            metric_type='gauge',
            value=100.5,
            tags={'environment': 'test'}
        )
        
        self.assertEqual(metric.name, 'test_metric')
        self.assertEqual(metric.metric_type, 'gauge')
        self.assertEqual(metric.value, 100.5)
        self.assertEqual(metric.tags['environment'], 'test')
        self.assertIsNotNone(metric.timestamp)
    
    def test_metric_str_representation(self):
        """
        تست نمایش string مدل Metric
        """
        metric = Metric.objects.create(
            name='test_metric',
            value=50.0
        )
        
        expected = f"test_metric: 50.0 ({metric.timestamp})"
        self.assertEqual(str(metric), expected)


class UserActivityModelTest(TestCase):
    """
    تست‌های مربوط به مدل UserActivity
    """
    
    def setUp(self):
        """
        تنظیمات اولیه برای تست‌ها
        """
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_user_activity_creation(self):
        """
        تست ایجاد فعالیت کاربر
        """
        activity = UserActivity.objects.create(
            user=self.user,
            action='login',
            resource='auth',
            ip_address='127.0.0.1',
            metadata={'browser': 'chrome'}
        )
        
        self.assertEqual(activity.user, self.user)
        self.assertEqual(activity.action, 'login')
        self.assertEqual(activity.resource, 'auth')
        self.assertEqual(activity.ip_address, '127.0.0.1')
        self.assertEqual(activity.metadata['browser'], 'chrome')
    
    def test_user_activity_str_representation(self):
        """
        تست نمایش string مدل UserActivity
        """
        activity = UserActivity.objects.create(
            user=self.user,
            action='view_profile'
        )
        
        expected = f"{self.user.username}: view_profile ({activity.timestamp})"
        self.assertEqual(str(activity), expected)


class PerformanceMetricModelTest(TestCase):
    """
    تست‌های مربوط به مدل PerformanceMetric
    """
    
    def setUp(self):
        """
        تنظیمات اولیه برای تست‌ها
        """
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_performance_metric_creation(self):
        """
        تست ایجاد متریک عملکرد
        """
        metric = PerformanceMetric.objects.create(
            endpoint='/api/users/',
            method='GET',
            response_time_ms=150,
            status_code=200,
            user=self.user
        )
        
        self.assertEqual(metric.endpoint, '/api/users/')
        self.assertEqual(metric.method, 'GET')
        self.assertEqual(metric.response_time_ms, 150)
        self.assertEqual(metric.status_code, 200)
        self.assertEqual(metric.user, self.user)
    
    def test_performance_metric_str_representation(self):
        """
        تست نمایش string مدل PerformanceMetric
        """
        metric = PerformanceMetric.objects.create(
            endpoint='/api/test/',
            method='POST',
            response_time_ms=200,
            status_code=201
        )
        
        expected = "POST /api/test/: 200ms (201)"
        self.assertEqual(str(metric), expected)


class AlertRuleModelTest(TestCase):
    """
    تست‌های مربوط به مدل AlertRule
    """
    
    def test_alert_rule_creation(self):
        """
        تست ایجاد قانون هشدار
        """
        rule = AlertRule.objects.create(
            name='High Response Time',
            metric_name='response_time',
            operator='gt',
            threshold=1000.0,
            severity='high'
        )
        
        self.assertEqual(rule.name, 'High Response Time')
        self.assertEqual(rule.metric_name, 'response_time')
        self.assertEqual(rule.operator, 'gt')
        self.assertEqual(rule.threshold, 1000.0)
        self.assertEqual(rule.severity, 'high')
        self.assertTrue(rule.is_active)
    
    def test_alert_rule_str_representation(self):
        """
        تست نمایش string مدل AlertRule
        """
        rule = AlertRule.objects.create(
            name='Test Rule',
            metric_name='test_metric',
            operator='gte',
            threshold=50.0
        )
        
        expected = "Test Rule: test_metric gte 50.0"
        self.assertEqual(str(rule), expected)


class AlertModelTest(TestCase):
    """
    تست‌های مربوط به مدل Alert
    """
    
    def setUp(self):
        """
        تنظیمات اولیه برای تست‌ها
        """
        self.rule = AlertRule.objects.create(
            name='Test Alert Rule',
            metric_name='test_metric',
            operator='gt',
            threshold=100.0
        )
    
    def test_alert_creation(self):
        """
        تست ایجاد هشدار
        """
        alert = Alert.objects.create(
            rule=self.rule,
            status='firing',
            metric_value=150.0,
            message='Test alert message'
        )
        
        self.assertEqual(alert.rule, self.rule)
        self.assertEqual(alert.status, 'firing')
        self.assertEqual(alert.metric_value, 150.0)
        self.assertEqual(alert.message, 'Test alert message')
        self.assertIsNone(alert.resolved_at)
    
    def test_alert_resolution(self):
        """
        تست حل هشدار
        """
        alert = Alert.objects.create(
            rule=self.rule,
            status='firing',
            metric_value=150.0,
            message='Test alert'
        )
        
        # حل هشدار
        alert.status = 'resolved'
        alert.resolved_at = timezone.now()
        alert.save()
        
        self.assertEqual(alert.status, 'resolved')
        self.assertIsNotNone(alert.resolved_at)
    
    def test_alert_str_representation(self):
        """
        تست نمایش string مدل Alert
        """
        alert = Alert.objects.create(
            rule=self.rule,
            status='firing',
            metric_value=120.0,
            message='Test alert'
        )
        
        expected = f"Test Alert Rule: firing ({alert.fired_at})"
        self.assertEqual(str(alert), expected)