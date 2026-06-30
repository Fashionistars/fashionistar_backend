"""
تست‌های مربوط به views اپ Analytics
"""
from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from ..models import Metric, UserActivity, PerformanceMetric, AlertRule, Alert

User = get_user_model()


class AnalyticsAPITestCase(APITestCase):
    """
    کلاس پایه برای تست‌های API Analytics
    """
    
    def setUp(self):
        """
        تنظیمات اولیه برای تست‌ها
        """
        self.user = User.objects.create_user(
            email='testuser1@analytics.test',
            password='testpass123'
        )
        self.admin_user = User.objects.create_superuser(
            email='admin@analytics.test',
            password='adminpass123'
        )


class MetricViewSetTest(AnalyticsAPITestCase):
    """
    تست‌های مربوط به MetricViewSet
    """
    
    def test_metrics_list_authenticated(self):
        """
        تست دریافت لیست متریک‌ها با کاربر احراز هویت شده
        """
        # ایجاد چند متریک نمونه
        Metric.objects.create(name='metric1', value=10.0)
        Metric.objects.create(name='metric2', value=20.0)
        
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:metric-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 2)
    
    def test_metrics_list_unauthenticated(self):
        """
        تست دریافت لیست متریک‌ها بدون احراز هویت
        """
        url = reverse('analytics:metric-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
    
    def test_metrics_list_filter_by_name(self):
        """
        تست فیلتر کردن متریک‌ها بر اساس نام
        """
        Metric.objects.create(name='test_metric', value=10.0)
        Metric.objects.create(name='other_metric', value=20.0)
        
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:metric-list')
        response = self.client.get(url, {'name': 'test'})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
        self.assertEqual(response.data['results'][0]['name'], 'test_metric')


class RecordMetricViewTest(AnalyticsAPITestCase):
    """
    تست‌های مربوط به record_metric view
    """
    
    def test_record_metric_success(self):
        """
        تست ثبت موفق متریک
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:record_metric')
        
        data = {
            'name': 'test_metric',
            'value': 42.5,
            'metric_type': 'gauge',
            'tags': {'environment': 'test'}
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_201_CREATED)
        self.assertEqual(response.data['name'], 'test_metric')
        self.assertEqual(response.data['value'], 42.5)
        
        # بررسی ذخیره در دیتابیس
        metric = Metric.objects.get(name='test_metric')
        self.assertEqual(metric.value, 42.5)
        self.assertEqual(metric.tags['environment'], 'test')
    
    def test_record_metric_invalid_data(self):
        """
        تست ثبت متریک با داده‌های نامعتبر
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:record_metric')
        
        data = {
            'name': '',  # نام خالی
            'value': 'invalid',  # مقدار نامعتبر
        }
        
        response = self.client.post(url, data, format='json')
        
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)


class UserAnalyticsViewTest(AnalyticsAPITestCase):
    """
    تست‌های مربوط به user_analytics view
    """
    
    def test_user_analytics_success(self):
        """
        تست دریافت موفق تحلیل‌های کاربر
        """
        # ایجاد چند فعالیت نمونه
        UserActivity.objects.create(user=self.user, action='login')
        UserActivity.objects.create(user=self.user, action='logout')
        
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:user_analytics')
        
        response = self.client.get(url, {'days': 7})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('total_activities', response.data)
        self.assertIn('unique_users', response.data)
        self.assertEqual(response.data['total_activities'], 2)
    
    def test_user_analytics_with_user_filter(self):
        """
        تست دریافت تحلیل‌های کاربر با فیلتر کاربر خاص
        """
        other_user = User.objects.create_user(
            email='other@analytics.test',
            password='testpass123'
        )
        
        UserActivity.objects.create(user=self.user, action='login')
        UserActivity.objects.create(user=other_user, action='login')
        
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:user_analytics')
        
        response = self.client.get(url, {'user_id': self.user.id, 'days': 7})
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data['total_activities'], 1)


class SystemOverviewViewTest(AnalyticsAPITestCase):
    """
    تست‌های مربوط به system_overview view
    """
    
    def test_system_overview_success(self):
        """
        تست دریافت موفق بررسی کلی سیستم
        """
        # ایجاد داده‌های نمونه
        UserActivity.objects.create(user=self.user, action='login')
        PerformanceMetric.objects.create(
            endpoint='/api/test/',
            method='GET',
            response_time_ms=100,
            status_code=200
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:system_overview')
        
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('active_users_24h', response.data)
        self.assertIn('avg_response_time_24h_ms', response.data)
        self.assertIn('total_requests_24h', response.data)


class AlertViewSetTest(AnalyticsAPITestCase):
    """
    تست‌های مربوط به AlertViewSet
    """
    
    def test_alerts_list_authenticated(self):
        """
        تست دریافت لیست هشدارها با کاربر احراز هویت شده
        """
        # ایجاد قانون هشدار و هشدار
        rule = AlertRule.objects.create(
            name='Test Rule',
            metric_name='test_metric',
            operator='gt',
            threshold=50.0
        )
        Alert.objects.create(
            rule=rule,
            metric_value=100.0,
            message='Test alert'
        )
        
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:alert-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(len(response.data['results']), 1)
    
    def test_resolve_all_alerts_admin_only(self):
        """
        تست حل تمام هشدارها - فقط ادمین
        """
        # ایجاد هشدار
        rule = AlertRule.objects.create(
            name='Test Rule',
            metric_name='test_metric',
            operator='gt',
            threshold=50.0
        )
        Alert.objects.create(
            rule=rule,
            status='firing',
            metric_value=100.0,
            message='Test alert'
        )
        
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('analytics:alert-resolve-all')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn('resolved_count', response.data)
        
        # بررسی حل شدن هشدار
        alert = Alert.objects.first()
        self.assertEqual(alert.status, 'resolved')
    
    def test_resolve_all_alerts_non_admin(self):
        """
        تست حل تمام هشدارها - کاربر غیر ادمین
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:alert-resolve-all')
        response = self.client.post(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)


class AlertRuleViewSetTest(AnalyticsAPITestCase):
    """
    تست‌های مربوط به AlertRuleViewSet
    """
    
    def test_alert_rules_admin_access(self):
        """
        تست دسترسی ادمین به قوانین هشدار
        """
        AlertRule.objects.create(
            name='Test Rule',
            metric_name='test_metric',
            operator='gt',
            threshold=50.0
        )
        
        self.client.force_authenticate(user=self.admin_user)
        url = reverse('analytics:alertrule-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertGreaterEqual(len(response.data), 1)
    
    def test_alert_rules_non_admin_access(self):
        """
        تست عدم دسترسی کاربر غیر ادمین به قوانین هشدار
        """
        self.client.force_authenticate(user=self.user)
        url = reverse('analytics:alertrule-list')
        response = self.client.get(url)
        
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)