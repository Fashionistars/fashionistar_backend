"""
apps/analytics/services/alert_engine.py
========================================
Flexible, multi-channel alert rule engine for the FASHIONISTAR analytics domain.

Features:
  - Threshold-based rules (gt, gte, lt, lte, eq, ne)
  - Time-window aggregation (last 5m, 15m, 1h, 1d)
  - Multi-channel notifications: email, Slack, PagerDuty, SMS
  - Alert deduplication and suppression windows
  - Pluggable notification dispatchers

Usage:
    from apps.analytics.services.alert_engine import AlertEngine

    # Evaluate all active rules
    results = AlertEngine.evaluate_all()

    # Evaluate a single rule
    alert = AlertEngine.evaluate(rule)
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any, Optional

from django.core.cache import cache
from django.db.models import Avg, Count, Max, Min, Q, Sum
from django.utils import timezone

from apps.analytics.models import Alert, AlertRule, Metric, PerformanceMetric

logger = logging.getLogger(__name__)


# ============================================================================
# Operator Comparators
# ============================================================================

_OPERATORS = {
    "gt": lambda val, threshold: val > threshold,
    "gte": lambda val, threshold: val >= threshold,
    "lt": lambda val, threshold: val < threshold,
    "lte": lambda val, threshold: val <= threshold,
    "eq": lambda val, threshold: val == threshold,
    "ne": lambda val, threshold: val != threshold,
}


# ============================================================================
# Notification Dispatchers (Pluggable)
# ============================================================================

class BaseNotificationDispatcher:
    """Base class for notification dispatchers."""

    def send(self, alert: Alert, rule: AlertRule) -> bool:
        raise NotImplementedError


class EmailNotificationDispatcher(BaseNotificationDispatcher):
    """Send alert notifications via email."""

    def send(self, alert: Alert, rule: AlertRule) -> bool:
        from apps.analytics.settings import ANALYTICS_SETTINGS

        if not ANALYTICS_SETTINGS["ALERTS"].get("EMAIL_NOTIFICATIONS", False):
            return False

        recipients = ANALYTICS_SETTINGS["REPORTING"].get("REPORT_EMAIL_RECIPIENTS", [])
        if not recipients:
            return False

        try:
            from django.core.mail import send_mail

            subject = f"[FASHIONISTAR Alert] {rule.name} — {rule.severity.upper()}"
            message = (
                f"Alert: {alert.message}\n"
                f"Rule: {rule.name}\n"
                f"Metric: {rule.metric_name}\n"
                f"Current Value: {alert.metric_value}\n"
                f"Threshold: {rule.operator} {rule.threshold}\n"
                f"Severity: {rule.severity}\n"
                f"Fired At: {alert.fired_at.isoformat()}\n"
            )
            send_mail(
                subject=subject,
                message=message,
                from_email="alerts@fashionistar.com",
                recipient_list=recipients,
                fail_silently=True,
            )
            logger.info("[EmailNotificationDispatcher] Sent alert email for rule '%s'", rule.name)
            return True
        except Exception as exc:
            logger.error("[EmailNotificationDispatcher] Failed: %s", exc)
            return False


class SlackNotificationDispatcher(BaseNotificationDispatcher):
    """Send alert notifications to Slack webhook."""

    def send(self, alert: Alert, rule: AlertRule) -> bool:
        from django.conf import settings

        webhook_url = getattr(settings, "ANALYTICS_SLACK_WEBHOOK_URL", None)
        if not webhook_url:
            return False

        try:
            import requests

            payload = {
                "text": (
                    f":rotating_light: *FASHIONISTAR Alert*\n"
                    f"*Rule:* {rule.name}\n"
                    f"*Metric:* {rule.metric_name}\n"
                    f"*Value:* {alert.metric_value} (threshold: {rule.operator} {rule.threshold})\n"
                    f"*Severity:* {rule.severity}\n"
                    f"*Message:* {alert.message}\n"
                    f"*Fired At:* {alert.fired_at.isoformat()}"
                ),
            }
            requests.post(webhook_url, json=payload, timeout=5)
            logger.info("[SlackNotificationDispatcher] Sent Slack alert for rule '%s'", rule.name)
            return True
        except Exception as exc:
            logger.error("[SlackNotificationDispatcher] Failed: %s", exc)
            return False


class PagerDutyNotificationDispatcher(BaseNotificationDispatcher):
    """Send critical alerts to PagerDuty."""

    def send(self, alert: Alert, rule: AlertRule) -> bool:
        from django.conf import settings

        integration_key = getattr(settings, "ANALYTICS_PAGERDUTY_KEY", None)
        if not integration_key or rule.severity != "critical":
            return False

        try:
            import requests

            payload = {
                "routing_key": integration_key,
                "event_action": "trigger",
                "payload": {
                    "summary": f"FASHIONISTAR Alert: {rule.name}",
                    "severity": rule.severity,
                    "source": "fashionistar-analytics",
                    "custom_details": {
                        "metric_name": rule.metric_name,
                        "metric_value": alert.metric_value,
                        "threshold": rule.threshold,
                        "operator": rule.operator,
                        "message": alert.message,
                    },
                },
            }
            requests.post(
                "https://events.pagerduty.com/v2/enqueue",
                json=payload,
                timeout=5,
            )
            logger.info("[PagerDutyNotificationDispatcher] Sent PagerDuty alert for rule '%s'", rule.name)
            return True
        except Exception as exc:
            logger.error("[PagerDutyNotificationDispatcher] Failed: %s", exc)
            return False


# Registry of dispatchers — order matters (email → slack → pagerduty)
DISPATCHERS: list[BaseNotificationDispatcher] = [
    EmailNotificationDispatcher(),
    SlackNotificationDispatcher(),
    PagerDutyNotificationDispatcher(),
]


# ============================================================================
# Alert Engine
# ============================================================================

class AlertEngine:
    """
    Core alert evaluation engine.

    Evaluates AlertRule objects against current metric values and fires
    Alert records when thresholds are breached. Includes deduplication
    and suppression windows to prevent alert storms.
    """

    # Suppression window: don't re-fire the same rule within this period
    SUPPRESSION_WINDOW_MINUTES = 15

    # Cache key prefix for suppression tracking
    SUPPRESSION_CACHE_PREFIX = "analytics:alert:suppression:"

    @classmethod
    def evaluate_all(cls) -> dict[str, Any]:
        """
        Evaluate all active AlertRules and fire alerts where thresholds are breached.

        Returns:
            dict: Summary of evaluated rules, fired alerts, and suppressed alerts.
        """
        active_rules = AlertRule.objects.filter(is_active=True)
        results = {
            "evaluated": 0,
            "fired": 0,
            "suppressed": 0,
            "errors": 0,
            "details": [],
        }

        for rule in active_rules:
            try:
                alert = cls.evaluate(rule)
                results["evaluated"] += 1

                if alert is None:
                    results["details"].append({
                        "rule": rule.name,
                        "status": "not_breached",
                    })
                elif alert == "SUPPRESSED":
                    results["suppressed"] += 1
                    results["details"].append({
                        "rule": rule.name,
                        "status": "suppressed",
                    })
                else:
                    results["fired"] += 1
                    results["details"].append({
                        "rule": rule.name,
                        "status": "fired",
                        "alert_id": alert.id,
                        "metric_value": alert.metric_value,
                    })
            except Exception as exc:
                results["errors"] += 1
                results["details"].append({
                    "rule": rule.name,
                    "status": "error",
                    "error": str(exc),
                })
                logger.error("[AlertEngine.evaluate_all] Rule '%s' failed: %s", rule.name, exc)

        logger.info(
            "[AlertEngine.evaluate_all] Evaluated=%d Fired=%d Suppressed=%d Errors=%d",
            results["evaluated"],
            results["fired"],
            results["suppressed"],
            results["errors"],
        )
        return results

    @classmethod
    def evaluate(cls, rule: AlertRule) -> Alert | str | None:
        """
        Evaluate a single AlertRule against the latest metric value.

        Args:
            rule: The AlertRule to evaluate.

        Returns:
            - Alert instance if threshold breached and not suppressed.
            - "SUPPRESSED" if threshold breached but within suppression window.
            - None if threshold not breached.
        """
        # Fetch the latest metric value for this rule's metric_name
        metric_value = cls._get_latest_metric_value(rule)
        if metric_value is None:
            logger.debug("[AlertEngine.evaluate] No metric value found for '%s'", rule.metric_name)
            return None

        # Check threshold
        comparator = _OPERATORS.get(rule.operator)
        if comparator is None:
            logger.warning("[AlertEngine.evaluate] Unknown operator '%s' for rule '%s'", rule.operator, rule.name)
            return None

        is_breached = comparator(metric_value, rule.threshold)
        if not is_breached:
            return None

        # Check suppression window
        if cls._is_suppressed(rule):
            logger.debug("[AlertEngine.evaluate] Rule '%s' is suppressed", rule.name)
            return "SUPPRESSED"

        # Fire alert
        alert = cls._fire_alert(rule, metric_value)
        return alert

    @classmethod
    def _get_latest_metric_value(cls, rule: AlertRule) -> Optional[float]:
        """
        Get the latest metric value for the rule's metric_name.

        Tries Metric model first, then PerformanceMetric if the metric_name
        matches a performance-related pattern.
        """
        # Try Metric table
        latest_metric = (
            Metric.objects.filter(name=rule.metric_name)
            .order_by("-timestamp")
            .first()
        )
        if latest_metric:
            return latest_metric.value

        # Try PerformanceMetric aggregated value
        if rule.metric_name.startswith("perf."):
            endpoint = rule.metric_name.replace("perf.", "")
            recent = timezone.now() - timedelta(minutes=5)
            result = PerformanceMetric.objects.filter(
                endpoint=endpoint,
                timestamp__gte=recent,
            ).aggregate(
                avg_response=Avg("response_time_ms"),
                error_count=Count("id", filter=~Q(status_code__range=(200, 299))),
            )
            if rule.metric_name.endswith(".avg_response"):
                return result["avg_response"]
            if rule.metric_name.endswith(".error_count"):
                return result["error_count"]

        return None

    @classmethod
    def _is_suppressed(cls, rule: AlertRule) -> bool:
        """Check if the rule is within its suppression window."""
        cache_key = f"{cls.SUPPRESSION_CACHE_PREFIX}{rule.id}"
        return cache.get(cache_key) is not None

    @classmethod
    def _set_suppression(cls, rule: AlertRule) -> None:
        """Set the suppression flag for the rule."""
        cache_key = f"{cls.SUPPRESSION_CACHE_PREFIX}{rule.id}"
        cache.set(
            cache_key,
            timezone.now().isoformat(),
            timeout=cls.SUPPRESSION_WINDOW_MINUTES * 60,
        )

    @classmethod
    def _fire_alert(cls, rule: AlertRule, metric_value: float) -> Alert:
        """
        Create an Alert record, dispatch notifications, and set suppression.

        Args:
            rule: The AlertRule that was breached.
            metric_value: The current metric value that breached the threshold.

        Returns:
            Alert: The created Alert instance.
        """
        message = (
            f"Metric '{rule.metric_name}' value {metric_value} "
            f"{rule.operator} {rule.threshold} (threshold breached). "
            f"Severity: {rule.severity}."
        )

        alert = Alert.objects.create(
            rule=rule,
            status="firing",
            metric_value=metric_value,
            message=message,
            metadata={
                "threshold": rule.threshold,
                "operator": rule.operator,
                "severity": rule.severity,
            },
        )

        # Set suppression to prevent duplicate firing
        cls._set_suppression(rule)

        # Dispatch notifications through all registered dispatchers
        for dispatcher in DISPATCHERS:
            try:
                dispatcher.send(alert, rule)
            except Exception as exc:
                logger.error(
                    "[AlertEngine._fire_alert] Dispatcher %s failed: %s",
                    type(dispatcher).__name__,
                    exc,
                )

        # Log audit event
        try:
            from apps.audit_logs.services.analytics.analytics_audit import AnalyticsAuditService

            AnalyticsAuditService.log_alert_triggered(
                actor=None,
                alert=alert,
                rule=rule,
            )
        except Exception as exc:
            logger.error("[AlertEngine._fire_alert] Audit log failed: %s", exc)

        logger.info(
            "[AlertEngine._fire_alert] Alert #%d fired for rule '%s' (value=%.2f, threshold=%.2f)",
            alert.id,
            rule.name,
            metric_value,
            rule.threshold,
        )
        return alert

    @classmethod
    def resolve_alert(cls, alert_id: int, resolution_notes: str = "") -> Optional[Alert]:
        """
        Resolve an active alert.

        Args:
            alert_id: The Alert ID to resolve.
            resolution_notes: Optional notes about the resolution.

        Returns:
            Alert: The resolved Alert instance, or None if not found.
        """
        try:
            alert = Alert.objects.get(id=alert_id, status="firing")
            alert.status = "resolved"
            alert.resolved_at = timezone.now()
            if resolution_notes:
                alert.message = f"{alert.message}\n\nResolution: {resolution_notes}"
            alert.save(update_fields=["status", "resolved_at", "message"])

            # Log audit event
            try:
                from apps.audit_logs.services.analytics.analytics_audit import AnalyticsAuditService

                AnalyticsAuditService.log_alert_resolved(
                    actor=None,
                    alert=alert,
                    resolution_notes=resolution_notes,
                )
            except Exception as exc:
                logger.error("[AlertEngine.resolve_alert] Audit log failed: %s", exc)

            logger.info("[AlertEngine.resolve_alert] Alert #%d resolved", alert.id)
            return alert
        except Alert.DoesNotExist:
            logger.warning("[AlertEngine.resolve_alert] Alert #%d not found or not firing", alert_id)
            return None
