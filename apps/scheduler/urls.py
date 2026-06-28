# apps/scheduler/urls.py
"""
URL patterns for the scheduler app (DRF compatibility and write operations).
"""
from django.urls import path, include
from rest_framework.routers import DefaultRouter

from .apis.sync.scheduler_views import (
    TaskDefinitionViewSet,
    ScheduledTaskViewSet,
    TaskExecutionViewSet,
    TaskAlertViewSet,
    TaskStatisticsView
)

app_name = 'scheduler'

router = DefaultRouter()
router.register(r'definitions', TaskDefinitionViewSet, basename='taskdefinition')
router.register(r'scheduled', ScheduledTaskViewSet, basename='scheduledtask')
router.register(r'executions', TaskExecutionViewSet, basename='taskexecution')
router.register(r'alerts', TaskAlertViewSet, basename='taskalert')
router.register(r'statistics', TaskStatisticsView, basename='statistics')

urlpatterns = [
    path('', include(router.urls)),
]