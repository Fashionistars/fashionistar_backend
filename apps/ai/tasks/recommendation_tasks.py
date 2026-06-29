# apps/ai/tasks/recommendation_tasks.py
"""
Celery tasks for the AI recommendation engine.

Tasks:
  run_profile_recommendations() — Generate recommendations for a MeasurementProfile
  embed_product()               — Embed a single product with FashionSigLIP
  embed_unembedded_products()   — Batch embed all products without embeddings

Queue: "ai" (dedicated queue for ML-heavy tasks)
"""

import logging

from celery import shared_task

logger = logging.getLogger(__name__)


@shared_task(
    bind=True,
    name="apps.ai.tasks.recommendation_tasks.run_profile_recommendations",
    queue="ai",
    max_retries=2,
    default_retry_delay=60,
    soft_time_limit=90,
    time_limit=120,
)
def run_profile_recommendations(
    self,
    profile_id: str,
    user_id: int,
    limit: int = 20,
) -> dict:
    """
    Generate measurement-aware product recommendations for a user's profile.

    Called by MeasurementWorkflow after a successful body scan.
    Results are cached in Redis for the Ninja recommendations endpoint.

    Flow:
      1. Load MeasurementProfile from DB
      2. Convert measurements to FashionSigLIP text embedding
      3. pgvector cosine similarity search against ProductEmbedding
      4. Filter by size availability
      5. Cache results (TTL=1 hour)

    Args:
        profile_id: MeasurementProfile ID
        user_id:    Owner user PK
        limit:      Number of recommendations to generate

    Returns:
        dict: {user_id, profile_id, recommendations: [{product_id, similarity}]}
    """
    logger.info("[run_profile_recommendations] profile=%s user=%s", profile_id, user_id)

    try:
        from apps.ai.database import FashionistarDatabaseLayer
        from apps.ai.engines.recommendation_engine import FashionEmbeddingEngine
        from django.core.cache import cache

        db = FashionistarDatabaseLayer()
        try:
            _profile_pk = int(profile_id)
        except (ValueError, TypeError):
            # profile_id may be a UUID string or non-integer — look up by PK string
            _profile_pk = profile_id
        measurements = db.get_measurement_profile(_profile_pk)

        if not measurements:
            logger.warning("[run_profile_recommendations] No profile found: %s", profile_id)
            return {"user_id": user_id, "profile_id": profile_id, "recommendations": []}

        # Generate measurement → fashion embedding
        engine = FashionEmbeddingEngine()
        query_vec = engine.embed_measurement_query(measurements)

        recommendations = []
        if query_vec:
            recommendations = _pgvector_similarity_search(query_vec, limit=limit)
        else:
            # Fallback: trending products if embedding unavailable
            recommendations = db.get_trending_products(days=7, limit=limit)

        result = {
            "user_id":        user_id,
            "profile_id":     profile_id,
            "recommendations": recommendations,
        }

        # Cache results for Ninja endpoint
        cache_key = f"ai:recommendations:user:{user_id}"
        cache.set(cache_key, result, timeout=3600)  # 1 hour TTL

        logger.info(
            "[run_profile_recommendations] Found %d recommendations for user %s",
            len(recommendations), user_id,
        )
        return result

    except Exception as exc:
        logger.exception("[run_profile_recommendations] FAILED profile=%s", profile_id)
        raise self.retry(exc=exc, countdown=60)


def _pgvector_similarity_search(query_vec: list[float], limit: int = 20) -> list[dict]:
    """
    pgvector cosine similarity search against ProductEmbedding.
    Returns top-k most similar products.
    """
    try:
        from django.db import connection

        # Use raw SQL for pgvector cosine similarity (django-pgvector ORM alternative)
        # Cosine distance: 1 - (a · b) / (|a| |b|) — lower = more similar
        vec_str = "[" + ",".join(str(round(v, 6)) for v in query_vec) + "]"

        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    pe.product_id,
                    1 - (pe.combined_vector <=> %s::vector) AS similarity
                FROM ai_productembedding pe
                JOIN product_product p ON pe.product_id = p.id
                WHERE p.is_active = true
                  AND pe.combined_vector IS NOT NULL
                ORDER BY pe.combined_vector <=> %s::vector
                LIMIT %s
                """,
                [vec_str, vec_str, limit],
            )
            rows = cursor.fetchall()

        return [
            {"product_id": row[0], "similarity": round(float(row[1]), 4)}
            for row in rows
        ]
    except Exception as exc:
        logger.warning("[_pgvector_similarity_search] failed: %s", exc)
        return []


@shared_task(
    bind=True,
    name="apps.ai.tasks.recommendation_tasks.embed_product",
    queue="ai",
    max_retries=3,
    default_retry_delay=120,
    soft_time_limit=300,
)
def embed_product(self, product_id: int) -> dict:
    """
    Generate and store FashionSigLIP embeddings for a single product.

    Called by: DB change signal when a Product is created/updated.
    Stores embeddings in ProductEmbedding model (pgvector).

    Args:
        product_id: Product PK

    Returns:
        dict: {product_id, status, model_version}
    """
    logger.info("[embed_product] product=%s", product_id)

    try:
        from apps.ai.database import FashionistarDatabaseLayer
        from apps.ai.engines.recommendation_engine import FashionEmbeddingEngine
        from apps.ai.models.product_embedding import ProductEmbedding

        db = FashionistarDatabaseLayer()
        product = db.get_product_full(product_id)

        # ── Fetch primary product image from Cloudinary ────────────────────
        image_bytes: bytes | None = None
        image_url: str | None = (
            product.get("primary_image_url")  # populated by get_product_full()
            or product.get("image_url")
        )
        if image_url:
            try:
                import urllib.request
                req = urllib.request.Request(
                    image_url,
                    headers={
                        "User-Agent": "FASHIONISTAR-AI-Embedder/1.0",
                        "Accept":     "image/*",
                    },
                )
                with urllib.request.urlopen(req, timeout=15) as resp:
                    image_bytes = resp.read()
                logger.debug(
                    "[embed_product] fetched %d bytes from Cloudinary for product %s",
                    len(image_bytes), product_id,
                )
            except Exception as img_exc:
                # Non-fatal: degrade to text-only embedding
                logger.warning(
                    "[embed_product] image fetch failed for product %s (%s) — using text-only",
                    product_id, img_exc,
                )
        # ── End image fetch ────────────────────────────────────────────────

        engine = FashionEmbeddingEngine()
        vectors = engine.embed_product(
            title=product.get("name", ""),
            description=product.get("description", ""),
            image_bytes=image_bytes,
        )

        if not vectors.get("combined_vector"):
            logger.warning("[embed_product] No embedding generated for product %s", product_id)
            return {"product_id": product_id, "status": "no_embedding"}

        ProductEmbedding.objects.update_or_create(
            product_id=product_id,
            defaults={
                "text_vector":     vectors["text_vector"],
                "image_vector":    vectors["image_vector"],
                "combined_vector": vectors["combined_vector"],
                "model_version":   "marqo-FashionSigLIP-B-16",
            },
        )

        return {"product_id": product_id, "status": "embedded", "model_version": "marqo-FashionSigLIP-B-16"}

    except Exception as exc:
        logger.exception("[embed_product] FAILED product=%s", product_id)
        raise self.retry(exc=exc, countdown=120)


@shared_task(
    name="apps.ai.tasks.recommendation_tasks.embed_unembedded_products",
    queue="ai",
    ignore_result=True,
    soft_time_limit=1800,  # 30 min max
)
def embed_unembedded_products() -> None:
    """
    Batch embed all active products that don't have embeddings yet.

    Called by: Celery Beat every 6 hours.
    Processes in batches of 50 to avoid memory issues on CPU.
    """
    logger.info("[embed_unembedded_products] Starting batch embedding")

    try:
        from django.apps import apps as django_apps

        Product = django_apps.get_model("product", "Product")
        # Find products without embeddings
        unembedded_ids = list(
            Product.objects
            .filter(is_active=True)
            .exclude(embedding__isnull=False)
            .values_list("id", flat=True)[:200]  # Max 200 per run
        )

        logger.info("[embed_unembedded_products] Found %d products to embed", len(unembedded_ids))

        for product_id in unembedded_ids:
            embed_product.delay(product_id)

    except Exception as exc:
        logger.exception("[embed_unembedded_products] FAILED: %s", exc)
