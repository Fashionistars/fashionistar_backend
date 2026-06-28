"""
URL routing برای اپ Analytics
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

# ایجاد router برای ViewSets
router = DefaultRouter()
router.register(r'metrics', views.MetricViewSet)
router.register(r'user-activities', views.UserActivityViewSet)
router.register(r'performance-metrics', views.PerformanceMetricViewSet)
router.register(r'business-metrics', views.BusinessMetricViewSet)
router.register(r'alert-rules', views.AlertRuleViewSet)
router.register(r'alerts', views.AlertViewSet)

app_name = 'analytics'

urlpatterns = [
    # ViewSets URLs
    path('', include(router.urls)),
    
    # Function-based views
    path('record-metric/', views.record_metric, name='record_metric'),
    path('user-analytics/', views.user_analytics, name='user_analytics'),
    path('performance-analytics/', views.performance_analytics, name='performance_analytics'),
    path('calculate-business-metrics/', views.calculate_business_metrics, name='calculate_business_metrics'),
    path('system-overview/', views.system_overview, name='system_overview'),
    path('check-alerts/', views.check_alerts, name='check_alerts'),
]