"""
apps/analytics/tasks/alert_evaluation_tasks.py
==============================================
Celery tasks for periodic alert rule evaluation.

Runs every minute via Celery Beat to evaluate all active AlertRules
against current metric values and fire alerts when thresholds are breached.

Queue: "analytics"
"""

from __future__ import annotations

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.analytics.tasks.alert_evaluation_tasks.evaluate_alert_rules",
    queue="analytics",
    soft_time_limit=60,
    time_limit=90,
    ignore_result=False,
)
def evaluate_alert_rules() -> dict:
    """
    Periodic task: evaluate all active AlertRules and fire alerts.

    Runs every minute via Celery Beat. Delegates to AlertEngine.evaluate_all().

    Returns:
        dict: Summary of evaluated rules, fired alerts, and suppressed alerts.
    """
    from apps.analytics.services.alert_engine import AlertEngine

    logger.info("[evaluate_alert_rules] Starting alert rule evaluation")

    try:
        results = AlertEngine.evaluate_all()
        logger.info(
            "[evaluate_alert_rules] DONE — Evaluated=%d Fired=%d Suppressed=%d Errors=%d",
            results["evaluated"],
            results["fired"],
            results["suppressed"],
            results["errors"],
        )
        return results
    except Exception as exc:
        logger.exception("[evaluate_alert_rules] FAILED: %s", exc)
        return {"status": "error", "error": str(exc)}
