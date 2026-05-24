"""
URL patterns برای اپ scheduler
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .views import (
    TaskDefinitionViewSet,
    ScheduledTaskViewSet,
    TaskExecutionViewSet,
    TaskAlertViewSet,
    TaskStatisticsView
)

app_name = 'scheduler'

# ایجاد router
router = DefaultRouter()
router.register(r'definitions', TaskDefinitionViewSet, basename='taskdefinition')
router.register(r'scheduled', ScheduledTaskViewSet, basename='scheduledtask')
router.register(r'executions', TaskExecutionViewSet, basename='taskexecution')
router.register(r'alerts', TaskAlertViewSet, basename='taskalert')
router.register(r'statistics', TaskStatisticsView, basename='statistics')

urlpatterns = [
    path('', include(router.urls)),
]