# apps/ai/signals/db_change_signals.py
"""
Django post_save signals → AI data ingestion pipeline.

When any watched model is saved, two things happen:
  1. FashionistarDatabaseLayer cache for that entity is invalidated (synchronous)
  2. A DBChangeEvent row is created (synchronous, lightweight)
  3. The ingestion Celery task is fired (async, non-blocking)

The signal handler is deliberately lightweight — it does not call any
external APIs or perform any computation. All heavy lifting is in Celery.

Watched models:
  - product.Product        → re-embed with FashionSigLIP, update product cache
  - measurements.MeasurementProfile → update user measurement cache
  - authentication.UnifiedUser      → update user context cache
  - order.Order            → update trending products, platform stats cache

Adding a new watched model:
  1. Add it to WATCHED_MODELS below
  2. Add a matching invalidate_*_cache() method to FashionistarDatabaseLayer
  3. The ingestion task will pick it up automatically
"""

import logging

from django.db.models.signals import post_save
from django.dispatch import receiver

logger = logging.getLogger(__name__)

# ── Models to watch for AI data changes ────────────────────────────────────────
# Format: (app_label, model_name, cache_invalidation_method_on_db_layer)
WATCHED_MODELS: list[tuple[str, str, str | None]] = [
    ("product",         "Product",              "invalidate_product_cache"),
    ("measurements",    "MeasurementProfile",   "invalidate_measurement_cache"),
    ("authentication",  "UnifiedUser",           "invalidate_user_cache"),
    ("order",           "Order",                 None),  # invalidate platform stats
]

# Build lookup set for O(1) signal dispatch
_WATCHED_LABELS: dict[str, str | None] = {
    f"{app}.{model}": cache_method
    for app, model, cache_method in WATCHED_MODELS
}


@receiver(post_save)
def _ai_db_change_handler(sender, instance, created: bool, **kwargs) -> None:
    """
    Central post_save handler for all AI-watched models.

    Performance: This handler does a single dict lookup and spawns
    one Celery task. No database queries, no network calls.
    """
    model_label = f"{instance._meta.app_label}.{instance._meta.model_name}"
    if model_label not in _WATCHED_LABELS:
        return

    # 1. Invalidate AI cache for this entity
    cache_method = _WATCHED_LABELS[model_label]
    if cache_method:
        try:
            from apps.ai.database import FashionistarDatabaseLayer
            db = FashionistarDatabaseLayer()
            getattr(db, cache_method)(instance.pk)
        except Exception as exc:
            logger.debug("AI cache invalidation skipped: %s", exc)

    # 2. Create DBChangeEvent and fire Celery ingestion task
    try:
        from apps.ai.tasks.ingestion_tasks import ingest_db_change
        ingest_db_change.delay(
            app_label=instance._meta.app_label,
            model_name=instance._meta.model_name,
            object_id=str(instance.pk),
            event_type="created" if created else "updated",
        )
    except Exception as exc:
        # Never let signal failure crash the main request
        logger.warning("AI ingestion signal failed for %s#%s: %s", model_label, instance.pk, exc)
