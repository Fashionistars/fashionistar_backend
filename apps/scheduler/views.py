# apps/scheduler/views.py
"""
Legacy wrapper for compatibility with sync imports.
All active code has been migrated to apis/sync/ and apis/async_/.
"""

from .apis.sync.scheduler_views import (  # noqa: F401
    TaskDefinitionViewSet,
    ScheduledTaskViewSet,
    TaskExecutionViewSet,
    TaskAlertViewSet,
    TaskStatisticsView
)