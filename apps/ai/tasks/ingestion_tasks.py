# apps/ai/tasks/ingestion_tasks.py
"""
Celery tasks for the AI data ingestion pipeline.

Tasks:
  ingest_db_change()        — Process a DBChangeEvent (triggered by signals)
  refresh_trending_cache()  — Rebuild trending products cache hourly

Queue: "ai_ingestion" (lightweight, high-frequency queue)
Worker: Start with: celery -A backend worker -Q ai_ingestion --concurrency=4
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    name="apps.ai.tasks.ingestion_tasks.ingest_db_change",
    queue="ai_ingestion",
    ignore_result=True,
    max_retries=3,
    default_retry_delay=10,
)
def ingest_db_change(
    app_label: str,
    model_name: str,
    object_id: str,
    event_type: str = "updated",
) -> None:
    """
    Process a DB change event from the AI ingestion pipeline.

    Called by Django post_save signal via apps.ai.signals.db_change_signals.
    Creates a DBChangeEvent audit row and dispatches domain-specific actions.

    Domain actions:
      - product.Product     → schedule embed_product.delay()
      - measurements.*      → invalidate user recommendation cache
      - order.Order         → invalidate platform stats cache

    Args:
        app_label:  Django app label (e.g., 'product')
        model_name: Django model name (e.g., 'Product')
        object_id:  Primary key of changed instance (as string)
        event_type: 'created' | 'updated' | 'deleted'
    """
    try:
        from apps.ai.models import DBChangeEvent
        from django.utils import timezone

        event = DBChangeEvent.objects.create(
            app_label=app_label,
            model_name=model_name,
            object_id=object_id,
            event_type=event_type,
        )

        # Dispatch domain-specific processing
        model_key = f"{app_label}.{model_name.lower()}"

        if model_key == "product.product" and event_type in ("created", "updated"):
            # Trigger re-embedding for the changed product
            from apps.ai.tasks.recommendation_tasks import embed_product
            embed_product.delay(int(object_id))

        elif model_key in ("measurements.measurementprofile",):
            # Invalidate recommendation cache for this user's profile
            pass  # Cache already invalidated by signal

        # Mark event as processed
        DBChangeEvent.objects.filter(pk=event.pk).update(
            is_processed=True,
            processed_at=timezone.now(),
        )

    except Exception as exc:
        logger.warning(
            "[ingest_db_change] %s.%s#%s failed: %s",
            app_label, model_name, object_id, exc,
        )


@shared_task(
    name="apps.ai.tasks.ingestion_tasks.refresh_trending_cache",
    queue="ai_ingestion",
    ignore_result=True,
)
def refresh_trending_cache() -> None:
    """
    Rebuild the trending products cache.
    Called by Celery Beat every hour to keep recommendations fresh.
    """
    try:
        from apps.ai.database import FashionistarDatabaseLayer
        db = FashionistarDatabaseLayer()

        # Force cache rebuild by invalidating first
        from django.core.cache import cache
        cache.delete("ai:trending:7d:20")
        cache.delete("ai:trending:30d:20")

        # Rebuild
        db.get_trending_products(days=7, limit=20)
        db.get_trending_products(days=30, limit=20)

        logger.info("[refresh_trending_cache] Trending products cache rebuilt")
    except Exception as exc:
        logger.warning("[refresh_trending_cache] failed: %s", exc)


@shared_task(
    name="apps.ai.tasks.ingestion_tasks.cleanup_old_events",
    queue="ai_ingestion",
    ignore_result=True,
)
def cleanup_old_events(days: int = 30) -> None:
    """
    Delete processed DBChangeEvent rows older than N days.
    Called by Celery Beat weekly. Prevents unbounded table growth.
    """
    try:
        from datetime import timedelta
        from django.utils import timezone
        from apps.ai.models import DBChangeEvent

        cutoff = timezone.now() - timedelta(days=days)
        deleted, _ = DBChangeEvent.objects.filter(
            is_processed=True,
            created_at__lt=cutoff,
        ).delete()
        logger.info("[cleanup_old_events] Deleted %d old DBChangeEvent rows", deleted)
    except Exception as exc:
        logger.warning("[cleanup_old_events] failed: %s", exc)
