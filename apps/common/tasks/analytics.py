# apps/common/tasks/analytics.py
"""
Model analytics background tasks.

Tasks:
    update_model_analytics_counter — Atomically update ModelAnalytics row.
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


# ================================================================
# MODEL ANALYTICS COUNTER (Background atomic update)
# ================================================================

@shared_task(
    name="update_model_analytics_counter",
    bind=True,
    max_retries=0,       # Fire-and-forget — no retries to stay fast
    ignore_result=True,
)
def update_model_analytics_counter(self, model_name, app_label, deltas):
    """
    Atomically update the ``ModelAnalytics`` row for
    ``model_name`` with the given ``deltas``.

    Runs as fire-and-forget so the HTTP request / admin action is NOT delayed.

    Uses ``SELECT ... FOR UPDATE`` inside ``transaction.atomic()``
    (via ``ModelAnalytics._adjust()``) to eliminate race conditions.

    Args:
        model_name (str): The Django model class name.
        app_label (str): The Django app label.
        deltas (dict): Mapping of field name → integer delta.
            Example: ``{'total_created': 1, 'total_active': 1}``
    """
    try:
        from apps.common.models import ModelAnalytics
        ModelAnalytics._adjust(
            model_name=model_name,
            app_label=app_label,
            **deltas,
        )
        logger.debug(
            "ModelAnalytics updated for %s: %s",
            model_name,
            deltas,
        )
    except Exception:
        logger.warning(
            "update_model_analytics_counter failed for %s: %s",
            model_name,
            deltas,
        )
