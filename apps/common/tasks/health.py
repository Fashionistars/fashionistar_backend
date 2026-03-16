# apps/common/tasks/health.py
"""
Health & availability tasks.

Tasks:
    keep_service_awake  — Periodic HTTP ping to prevent Render free-tier spin-down.
"""

import logging

import requests
from celery import shared_task
from django.conf import settings

logger = logging.getLogger(__name__)


# ================================================================
# SERVICE HEALTH PING
# ================================================================

@shared_task(
    name="keep_service_awake",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
)
def keep_service_awake(self):
    """
    Periodic task that pings the application URL to prevent
    Render free-tier spin-down.

    Retries up to 2 times on failure with a 30-second delay.
    """
    site_url = getattr(settings, "SITE_URL", None)

    if not site_url:
        logger.warning(
            "SITE_URL is not configured. "
            "Cannot run keep_service_awake task."
        )
        return

    try:
        response = requests.get(site_url, timeout=15)
        if response.status_code == 200:
            logger.info(
                "Successfully pinged %s to keep service awake",
                site_url,
            )
        else:
            logger.error(
                "Failed to ping %s. Status: %s",
                site_url,
                response.status_code,
            )
    except requests.exceptions.RequestException as exc:
        logger.error("Error pinging %s: %s", site_url, exc)
        raise self.retry(exc=exc)
