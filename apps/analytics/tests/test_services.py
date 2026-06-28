"""
تست‌های مربوط به services اپ Analytics
"""
from django.test import TestCase
from django.contrib.auth import get_user_model
from django.utils import timezone
from datetime import timedelta
from unittest.mock import patch, MagicMock

from ..services import AnalyticsService, MetricsService, ReportingService, InsightsService
from ..models import Metric, UserActivity, PerformanceMetric, AlertRule, Alert

User = get_user_model()


class AnalyticsServiceTest(TestCase):
    """
    تست‌های مربوط به کلاس AnalyticsService
    """
    
    def setUp(self):
        """
        تنظیمات اولیه برای تست‌ها
        """
        self.analytics_service = AnalyticsService()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_record_metric(self):
        """
        تست ثبت متریک
        """
        metric = self.analytics_service.record_metric(
            name='test_metric',
            value=100.5,
            metric_type='gauge',
            tags={'environment': 'test'}
        )
        
        self.assertIsInstance(metric, Metric)
        self.assertEqual(metric.name, 'test_metric')
        self.assertEqual(metric.value, 100.5)
        self.assertEqual(metric.metric_type, 'gauge')
        self.assertEqual(metric.tags['environment'], 'test')
    
    def test_record_user_activity(self):
        """
        تست ثبت فعالیت کاربر
        """
        activity = self.analytics_service.record_user_activity(
            user=self.user,
            action='login',
            resource='auth',
            metadata={'test': 'data'}
        )
        
        self.assertIsInstance(activity, UserActivity)
        self.assertEqual(activity.user, self.user)
        self.assertEqual(activity.action, 'login')
        self.assertEqual(activity.resource, 'auth')
        self.assertEqual(activity.metadata['test'], 'data')
    
    def test_record_user_activity_with_request(self):
        """
        تست ثبت فعالیت کاربر با request
        """
        # ایجاد mock request
        mock_request = MagicMock()
        mock_request.META = {
            'HTTP_USER_AGENT': 'Test Browser',
            'REMOTE_ADDR': '127.0.0.1'
        }
        mock_request.session.session_key = 'test_session'
        
        activity = self.analytics_service.record_user_activity(
            user=self.user,
            action='view_page',
            request=mock_request
        )
        
        self.assertEqual(activity.ip_address, '127.0.0.1')
        self.assertEqual(activity.user_agent, 'Test Browser')
        self.assertEqual(activity.session_id, 'test_session')
    
    def test_record_performance_metric(self):
        """
        تست ثبت متریک عملکرد
        """
        metric = self.analytics_service.record_performance_metric(
            endpoint='/api/test/',
            method='GET',
            response_time_ms=150,
            status_code=200,
            user=self.user
        )
        
        self.assertIsInstance(metric, PerformanceMetric)
        self.assertEqual(metric.endpoint, '/api/test/')
        self.assertEqual(metric.method, 'GET')
        self.assertEqual(metric.response_time_ms, 150)
        self.assertEqual(metric.status_code, 200)
        self.assertEqual(metric.user, self.user)
    
    def test_get_user_analytics(self):
        """
        تست دریافت تحلیل‌های کاربر
        """
        # ایجاد چند فعالیت نمونه
        UserActivity.objects.create(
            user=self.user,
            action='login',
            resource='auth'
        )
        UserActivity.objects.create(
            user=self.user,
            action='view_profile',
            resource='profile'
        )
        
        analytics = self.analytics_service.get_user_analytics(days=7)
        
        self.assertIn('total_activities', analytics)
        self.assertIn('unique_users', analytics)
        self.assertIn('activity_breakdown', analytics)
        self.assertEqual(analytics['total_activities'], 2)
        self.assertEqual(analytics['unique_users'], 1)
    
    def test_get_performance_analytics(self):
        """
        تست دریافت تحلیل‌های عملکرد
        """
        # ایجاد چند متریک عملکرد نمونه
        PerformanceMetric.objects.create(
            endpoint='/api/users/',
            method='GET',
            response_time_ms=100,
            status_code=200
        )
        PerformanceMetric.objects.create(
            endpoint='/api/users/',
            method='POST',
            response_time_ms=200,
            status_code=201
        )
        
        analytics = self.analytics_service.get_performance_analytics(days=7)
        
        self.assertIn('total_requests', analytics)
        self.assertIn('avg_response_time_ms', analytics)
        self.assertIn('status_breakdown', analytics)
        self.assertEqual(analytics['total_requests'], 2)
    
    def test_check_alert_rules(self):
        """
        تست بررسی قوانین هشدار
        """
        # ایجاد قانون هشدار
        rule = AlertRule.objects.create(
            name='Test Alert',
            metric_name='test_metric',
            operator='gt',
            threshold=50.0,
            severity='medium'
        )
        
        # ایجاد متریک که شرط هشدار را برآورده می‌کند
        Metric.objects.create(
            name='test_metric',
            value=100.0,
            timestamp=timezone.now()
        )
        
        triggered_alerts = self.analytics_service.check_alert_rules()
        
        self.assertEqual(len(triggered_alerts), 1)
        self.assertEqual(triggered_alerts[0]['rule_name'], 'Test Alert')
        
        # بررسی ایجاد هشدار در دیتابیس
        alert = Alert.objects.filter(rule=rule, status='firing').first()
        self.assertIsNotNone(alert)
    
    def test_get_system_overview(self):
        """
        تست دریافت بررسی کلی سیستم
        """
        # ایجاد داده‌های نمونه
        UserActivity.objects.create(user=self.user, action='login')
        PerformanceMetric.objects.create(
            endpoint='/api/test/',
            method='GET',
            response_time_ms=100,
            status_code=200
        )
        
        overview = self.analytics_service.get_system_overview()
        
        self.assertIn('active_users_24h', overview)
        self.assertIn('avg_response_time_24h_ms', overview)
        self.assertIn('total_requests_24h', overview)
        self.assertIn('active_alerts', overview)


class MetricsServiceTest(TestCase):
    """
    تست‌های مربوط به کلاس MetricsService
    """
    
    def setUp(self):
        """
        تنظیمات اولیه برای تست‌ها
        """
        self.metrics_service = MetricsService()
        self.user = User.objects.create_user(
            username='testuser',
            password='testpass123'
        )
    
    def test_track_metric(self):
        """
        تست ردیابی متریک
        """
        metric = self.metrics_service.track_metric(
            user=self.user,
            metric_type='test_metric',
            value=42.0,
            metadata={'test': 'data'}
        )
        
        self.assertIsInstance(metric, Metric)
        self.assertEqual(metric.name, 'test_metric')
        self.assertEqual(metric.value, 42.0)
        self.assertEqual(metric.metric_type, 'gauge')
        self.assertEqual(metric.tags['test'], 'data')


class ReportingServiceTest(TestCase):
    """
    تست‌های مربوط به کلاس ReportingService
    """
    
    def setUp(self):
        """
        تنظیمات اولیه برای تست‌ها
        """
        self.reporting_service = ReportingService()
    
    def test_get_user_metrics(self):
        """
        تست دریافت متریک‌های کاربر
        """
        start_date = timezone.now() - timedelta(days=1)
        end_date = timezone.now()
        
        # ایجاد چند متریک نمونه
        Metric.objects.create(name='test1', value=10.0)
        Metric.objects.create(name='test2', value=20.0)
        
        metrics = self.reporting_service.get_user_metrics(
            user_id=1,
            start_date=start_date,
            end_date=end_date
        )
        
        self.assertIn('total_metrics', metrics)
        self.assertEqual(metrics['total_metrics'], 2)


class InsightsServiceTest(TestCase):
    """
    تست‌های مربوط به کلاس InsightsService
    """
    
    def setUp(self):
        """
        تنظیمات اولیه برای تست‌ها
        """
        self.insights_service = InsightsService()
    
    def test_get_dashboard_metrics(self):
        """
        تست دریافت متریک‌های داشبورد
        """
        metrics = self.insights_service.get_dashboard_metrics()
        
        self.assertIn('uptime', metrics)
        self.assertIn('users_active', metrics)
        self.assertEqual(metrics['uptime'], 100)
        self.assertEqual(metrics['users_active'], 0)