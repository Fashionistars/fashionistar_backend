# apps/ai/tasks/embedding_tasks.py
"""
Celery tasks for AI product embedding generation.

Tasks:
  generate_product_embedding()    — Generate FashionSigLIP embedding for one product
  batch_generate_embeddings()     — Bulk process a list of product IDs
  backfill_missing_embeddings()   — Cron task: find products without embeddings and fill them

Queue: "ai" (dedicated queue for ML-heavy tasks)
Worker: Start with: celery -A backend worker -Q ai --concurrency=1 --loglevel=info
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.ai.tasks.embedding_tasks.generate_product_embedding",
    queue="ai",
    max_retries=3,
    default_retry_delay=60,
    soft_time_limit=180,
    time_limit=210,
)
def generate_product_embedding(self, product_id: int) -> dict:
    """
    Generate and persist a FashionSigLIP embedding for a single product.

    Pipeline:
    1. Load product with images + description from DB
    2. Download primary product image (JPEG)
    3. Pass image + text through FashionSigLIP encoder → 512-dim vector
    4. Upsert ProductEmbedding model with the new vector
    5. pgvector HNSW index auto-updates on save

    Called by:
    - post_save signal when a new product is created/updated (ingestion_tasks.py)
    - batch_generate_embeddings() for bulk backfill
    - Vendor product publish flow (future hook)

    Args:
        product_id: Product PK

    Returns:
        dict: {product_id, embedding_dim, success}
    """
    logger.info("[generate_product_embedding] product_id=%s", product_id)

    try:
        from apps.ai.engines.recommendation_engine import FashionEmbeddingEngine
        from apps.ai.models.product_embedding import ProductEmbedding

        # Load product data
        from django.apps import apps
        Product = apps.get_model("product", "Product")

        try:
            product = Product.objects.select_related(
                "category", "vendor"
            ).prefetch_related("images").get(pk=product_id)
        except Product.DoesNotExist:
            logger.warning("[generate_product_embedding] Product %s not found", product_id)
            return {"product_id": product_id, "success": False, "error": "Product not found"}

        # Build text description for embedding
        text_desc = _build_product_text(product)

        # Get primary image URL
        image_url = _get_product_image_url(product)

        # Generate embedding
        engine = FashionEmbeddingEngine()
        if image_url:
            embedding = engine.embed_product(image_url=image_url, text=text_desc)
        else:
            embedding = engine.embed_text(text_desc)

        # Upsert ProductEmbedding
        ProductEmbedding.objects.update_or_create(
            product_id=product_id,
            defaults={
                "embedding":      embedding,
                "text_used":      text_desc[:500],
                "image_url_used": image_url or "",
                "model_version":  engine.model_name,
                "embedding_dim":  len(embedding),
            },
        )

        logger.info(
            "[generate_product_embedding] SUCCESS product=%s dim=%d",
            product_id, len(embedding),
        )
        return {
            "product_id":    product_id,
            "embedding_dim": len(embedding),
            "success":       True,
        }

    except Exception as exc:
        logger.exception("[generate_product_embedding] FAILED product=%s", product_id)
        raise self.retry(exc=exc, countdown=60)


@shared_task(
    bind=True,
    name="apps.ai.tasks.embedding_tasks.batch_generate_embeddings",
    queue="ai",
    max_retries=1,
    soft_time_limit=3600,   # 1 hour max for large batch
    time_limit=3660,
)
def batch_generate_embeddings(self, product_ids: list[int]) -> dict:
    """
    Generate embeddings for a batch of product IDs.

    Processes sequentially (to avoid OOM on small servers), tracking
    success/failure per product.

    Args:
        product_ids: List of Product PKs

    Returns:
        dict: {total, success_count, failed_count, failed_ids}
    """
    logger.info("[batch_generate_embeddings] batch_size=%d", len(product_ids))

    success_count = 0
    failed_ids: list[int] = []

    for product_id in product_ids:
        try:
            # Call synchronously within this task (no nested Celery for ML)
            generate_product_embedding.apply(args=[product_id])
            success_count += 1
        except Exception as exc:
            logger.warning(
                "[batch_generate_embeddings] product=%s failed: %s", product_id, exc
            )
            failed_ids.append(product_id)

    result = {
        "total":         len(product_ids),
        "success_count": success_count,
        "failed_count":  len(failed_ids),
        "failed_ids":    failed_ids,
    }
    logger.info("[batch_generate_embeddings] DONE: %s", result)
    return result


@shared_task(
    name="apps.ai.tasks.embedding_tasks.backfill_missing_embeddings",
    queue="ai",
    soft_time_limit=7200,   # 2 hours max for full backfill
    time_limit=7260,
    ignore_result=False,
)
def backfill_missing_embeddings(limit: int = 500) -> dict:
    """
    Periodic cron task: find all active products that do NOT have a
    ProductEmbedding record and generate their embeddings.

    Designed to run:
    - Once after initial deployment (to backfill existing products)
    - Weekly thereafter (to catch any products that slipped through)

    Args:
        limit: Maximum number of products to process in one run (default: 500)

    Returns:
        dict: {found, submitted}
    """
    logger.info("[backfill_missing_embeddings] Starting backfill (limit=%d)", limit)

    try:
        from django.apps import apps
        from apps.ai.models.product_embedding import ProductEmbedding

        Product = apps.get_model("product", "Product")

        # Find products without an embedding
        embedded_ids = set(
            ProductEmbedding.objects.values_list("product_id", flat=True)
        )
        missing_ids = list(
            Product.objects.filter(is_active=True)
            .exclude(id__in=embedded_ids)
            .values_list("id", flat=True)[:limit]
        )

        if not missing_ids:
            logger.info("[backfill_missing_embeddings] No missing embeddings found.")
            return {"found": 0, "submitted": 0}

        logger.info(
            "[backfill_missing_embeddings] Found %d products needing embeddings",
            len(missing_ids),
        )

        # Submit as a single batch task
        batch_generate_embeddings.delay(missing_ids)

        return {"found": len(missing_ids), "submitted": len(missing_ids)}

    except Exception as exc:
        logger.exception("[backfill_missing_embeddings] FAILED")
        return {"found": 0, "submitted": 0, "error": str(exc)}


# ── Private helpers ────────────────────────────────────────────────────────────

def _build_product_text(product) -> str:
    """Compose the text string used as input to the FashionSigLIP text encoder."""
    parts: list[str] = []

    if hasattr(product, "name") and product.name:
        parts.append(product.name)

    if hasattr(product, "category") and product.category:
        cat_name = getattr(product.category, "name", None)
        if cat_name:
            parts.append(cat_name)

    if hasattr(product, "description") and product.description:
        # Truncate to 200 chars — CLIP text encoder has a 77-token limit
        parts.append(product.description[:200])

    if hasattr(product, "tags"):
        try:
            tags = product.tags.values_list("name", flat=True)[:5]
            parts.extend(list(tags))
        except Exception:
            pass

    return " | ".join(parts) if parts else "fashion clothing"


def _get_product_image_url(product) -> str | None:
    """Return the primary product image URL (Cloudinary URL preferred)."""
    try:
        images = product.images.filter(is_primary=True).order_by("-created_at")
        if images.exists():
            img = images.first()
            return getattr(img, "cloudinary_url", None) or getattr(img, "url", None)

        # Fallback: any image
        img = product.images.first()
        if img:
            return getattr(img, "cloudinary_url", None) or getattr(img, "url", None)
    except Exception as exc:
        logger.debug("[_get_product_image_url] %s", exc)

    return None
