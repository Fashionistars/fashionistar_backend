# apps/ai/apis/async_api/ai_router.py
"""
Django Ninja async router for AI read endpoints.

All endpoints are READ-ONLY (GET) — no writes happen here.
Writes go through DRF sync endpoints (apps/measurements/apis/sync/).

Mounted at: /api/v1/ninja/ai/

Endpoints:
  GET  /api/v1/ninja/ai/scan/{session_id}/status/     — Scan session status
  GET  /api/v1/ninja/ai/recommendations/              — User product recommendations
  GET  /api/v1/ninja/ai/analytics/platform/           — Platform analytics report
  GET  /api/v1/ninja/ai/analytics/vendor/{vendor_id}/ — Vendor analytics report
  GET  /api/v1/ninja/ai/size-advice/{product_id}/     — AI size advice for product
"""

from __future__ import annotations

import json
import logging

from django.core.cache import cache
from ninja import Router, Schema
from ninja.security import django_auth

logger = logging.getLogger(__name__)

router = Router(tags=["AI Engine"])


# ─── Response Schemas ─────────────────────────────────────────────────────────

class ScanStatusSchema(Schema):
    session_id:              str
    status:                  str              # pending | processing | completed | failed
    scan_confidence:         float | None = None
    extracted_measurements:  dict | None = None
    error_message:           str  | None = None
    measurement_profile_id:  int  | None = None
    processing_started_at:   str  | None = None
    completed_at:            str  | None = None


class RecommendationSchema(Schema):
    product_id:  int
    final_score: float
    sim_score:   float
    trending:    bool = False


class RecommendationsResponseSchema(Schema):
    cached:       bool = True
    generated_at: str | None = None
    recommendations: list[RecommendationSchema] = []


class AnalyticsReportSchema(Schema):
    generated_at:    str
    days:            int
    scope:           str
    order_metrics:   dict = {}
    product_metrics: dict = {}
    user_metrics:    dict = {}
    vendor_metrics:  dict = {}
    anomalies:       list = []
    llm_insights:    str  = ""


class SizeAdviceSchema(Schema):
    product_id:       int
    recommended_size: str | None = None
    advice_text:      str = ""
    confidence:       float = 0.0
    llm_generated:    bool = False


# ─── Endpoints ────────────────────────────────────────────────────────────────


@router.get(
    "/scan/{session_id}/status/",
    auth=django_auth,
    response=ScanStatusSchema,
    summary="Get body scan session status",
    description=(
        "Poll this endpoint every 2 seconds after submitting landmarks. "
        "Returns 'completed' once the Celery MeasurementWorkflow finishes."
    ),
    operation_id="ai_scan_status",
)
async def get_scan_status(request, session_id: str) -> dict:
    """
    GET /api/v1/ninja/ai/scan/{session_id}/status/

    Real-time scan session status.

    Status values:
      pending    — Session created, landmarks not yet submitted
      processing — Celery task running measurement workflow
      completed  — Measurements saved to MeasurementProfile
      failed     — Processing error (see error_message)
    """
    from apps.measurements.models.scan import BodyScanSession
    from asgiref.sync import sync_to_async

    get_session = sync_to_async(
        lambda: BodyScanSession.objects.filter(
            session_id=session_id,
            owner=request.user,
        ).first()
    )

    session = await get_session()

    if not session:
        return {
            "session_id":  session_id,
            "status":      "failed",
            "error_message": "Session not found or unauthorised.",
        }

    profile_id = None
    if hasattr(session, "measurement_profile") and session.measurement_profile:
        profile_id = session.measurement_profile.id

    return {
        "session_id":             str(session.session_id),
        "status":                 session.status,
        "scan_confidence":        getattr(session, "scan_confidence", None),
        "extracted_measurements": getattr(session, "extracted_measurements", None),
        "error_message":          getattr(session, "error_message", None),
        "measurement_profile_id": profile_id,
        "processing_started_at":  (
            session.processing_started_at.isoformat()
            if getattr(session, "processing_started_at", None)
            else None
        ),
        "completed_at": (
            session.completed_at.isoformat()
            if getattr(session, "completed_at", None)
            else None
        ),
    }


@router.get(
    "/recommendations/",
    auth=django_auth,
    response=RecommendationsResponseSchema,
    summary="Get AI product recommendations for authenticated user",
    description=(
        "Returns personalised product recommendations based on the user's "
        "body measurements and purchase history. Served from Redis cache (TTL 1h)."
    ),
    operation_id="ai_recommendations",
)
async def get_recommendations(request) -> dict:
    """
    GET /api/v1/ninja/ai/recommendations/

    Returns the user's latest AI recommendations.
    Triggers a background re-computation if cache is stale (>1 hour old).
    """
    user_id   = request.user.id
    cache_key = f"ai:recommendations:user:{user_id}"

    cached = cache.get(cache_key)
    if cached:
        try:
            data = json.loads(cached) if isinstance(cached, str) else cached
            return {
                "cached":         True,
                "generated_at":   data[0].get("generated_at") if data and isinstance(data, list) else None,
                "recommendations": [
                    {
                        "product_id":  r.get("product_id"),
                        "final_score": r.get("final_score", 0),
                        "sim_score":   r.get("sim_score", 0),
                        "trending":    r.get("trending", False),
                    }
                    for r in (data if isinstance(data, list) else [])
                ],
            }
        except Exception as exc:
            logger.warning("[get_recommendations] Cache parse error: %s", exc)

    # Trigger async re-computation (non-blocking — returns empty for now)
    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def trigger_recommendation():
            from apps.measurements.models import MeasurementProfile
            profile = MeasurementProfile.objects.filter(
                owner_id=user_id, is_default=True
            ).first()
            if profile:
                from apps.ai.tasks.recommendation_tasks import run_profile_recommendations
                run_profile_recommendations.delay(
                    profile_id=str(profile.id),
                    user_id=user_id,
                )

        await trigger_recommendation()
    except Exception as exc:
        logger.warning("[get_recommendations] Trigger failed: %s", exc)

    return {
        "cached":          False,
        "generated_at":    None,
        "recommendations": [],
    }


@router.get(
    "/analytics/platform/",
    auth=django_auth,
    response=AnalyticsReportSchema,
    summary="Get platform analytics report",
    description=(
        "Returns the latest analytics report for the platform. "
        "Served from Redis cache (generated daily at 02:30 UTC). "
        "Requires staff or admin access."
    ),
    operation_id="ai_analytics_platform",
)
async def get_platform_analytics(
    request,
    days: int = 7,
) -> dict:
    """GET /api/v1/ninja/ai/analytics/platform/?days=7"""
    from ninja.errors import HttpError

    if not (request.user.is_staff or request.user.is_superuser):
        raise HttpError(403, "Staff access required.")

    cache_key = f"ai:analytics:platform:platform:{days}d"
    cached = cache.get(cache_key)

    if cached:
        try:
            return json.loads(cached) if isinstance(cached, str) else cached
        except Exception:
            pass

    # Trigger generation if not cached
    try:
        from asgiref.sync import sync_to_async

        @sync_to_async
        def trigger():
            from apps.ai.tasks.analytics_tasks import run_platform_analytics
            run_platform_analytics.delay(days=days)

        await trigger()
    except Exception as exc:
        logger.warning("[get_platform_analytics] Trigger failed: %s", exc)

    from django.utils import timezone
    return {
        "generated_at":    timezone.now().isoformat(),
        "days":            days,
        "scope":           "platform",
        "order_metrics":   {},
        "product_metrics": {},
        "user_metrics":    {},
        "vendor_metrics":  {},
        "anomalies":       [],
        "llm_insights":    "Report generation in progress...",
    }


@router.get(
    "/size-advice/{product_id}/",
    auth=django_auth,
    response=SizeAdviceSchema,
    summary="Get AI size recommendation for a product",
    description=(
        "Uses the user's default MeasurementProfile + Ollama LLM to "
        "generate a size recommendation for the specified product."
    ),
    operation_id="ai_size_advice",
)
async def get_size_advice(request, product_id: int) -> dict:
    """GET /api/v1/ninja/ai/size-advice/{product_id}/"""
    user_id   = request.user.id
    cache_key = f"ai:size_advice:{user_id}:{product_id}"

    cached = cache.get(cache_key)
    if cached:
        try:
            return json.loads(cached) if isinstance(cached, str) else cached
        except Exception:
            pass

    from asgiref.sync import sync_to_async

    @sync_to_async
    def generate_advice():
        from apps.measurements.models import MeasurementProfile
        from django.apps import apps

        # Get user's default measurement profile
        profile = MeasurementProfile.objects.filter(
            owner_id=user_id, is_default=True
        ).first()

        if not profile:
            return {
                "product_id":       product_id,
                "recommended_size": None,
                "advice_text":      "Add a body measurement profile to get size advice.",
                "confidence":       0.0,
                "llm_generated":    False,
            }

        # Get product info
        try:
            Product = apps.get_model("product", "Product")
            product = Product.objects.select_related("category").get(pk=product_id)
        except Exception:
            return {
                "product_id":       product_id,
                "recommended_size": None,
                "advice_text":      "Product not found.",
                "confidence":       0.0,
                "llm_generated":    False,
            }

        # Build measurements dict
        measurements = {
            k: getattr(profile, k, None)
            for k in ["height", "shoulder_width", "bust", "waist", "hips", "inseam"]
        }

        product_info = {
            "name":       product.name,
            "category":   getattr(product.category, "name", ""),
            "size_chart": [],   # TODO: load from ProductVariant size chart
        }

        # Get LLM advice
        try:
            from apps.ai.engines.llm_engine import OllamaLLMEngine
            engine = OllamaLLMEngine()
            if engine.is_available():
                advice_text = engine.generate_size_recommendation(
                    measurements=measurements,
                    product_info=product_info,
                )
                result = {
                    "product_id":       product_id,
                    "recommended_size": None,   # TODO: parse from advice_text
                    "advice_text":      advice_text,
                    "confidence":       0.75,
                    "llm_generated":    True,
                }
            else:
                result = {
                    "product_id":       product_id,
                    "recommended_size": None,
                    "advice_text":      "AI size advisor is warming up. Please try again shortly.",
                    "confidence":       0.0,
                    "llm_generated":    False,
                }
        except Exception as exc:
            logger.warning("[get_size_advice] LLM error: %s", exc)
            result = {
                "product_id":       product_id,
                "recommended_size": None,
                "advice_text":      "",
                "confidence":       0.0,
                "llm_generated":    False,
            }

        # Cache for 30 minutes
        import json
        cache.set(cache_key, json.dumps(result, default=str), timeout=1800)
        return result

    return await generate_advice()


class VendorAnalyticsSchema(Schema):
    vendor_id:       int
    generated_at:    str
    days:            int
    scope:           str
    order_metrics:   dict = {}
    product_metrics: dict = {}
    user_metrics:    dict = {}
    vendor_metrics:  dict = {}
    anomalies:       list = []
    llm_insights:    str  = ""


class AIHealthSchema(Schema):
    status:           str          # "healthy" | "degraded" | "unavailable"
    ollama_available: bool
    siglip_available: bool
    pgvector_ready:   bool
    mediapipe_ready:  bool
    checked_at:       str
    ai_engine_url:    str = ""    # URL of the remote AI Engine space (for debugging)
    ai_engine_status: str = ""    # "ok" | "unreachable" | "cold_starting"


# ─── Health Check Endpoint ─────────────────────────────────────────────────────


@router.get(
    "/health/",
    response=AIHealthSchema,
    summary="AI engine sub-system health check",
    description=(
        "Reports availability of all AI sub-systems: Ollama LLM, "
        "FashionSigLIP text encoder, pgvector HNSW index, and MediaPipe. "
        "SigLIP and MediaPipe live in the remote HF AI Engine ZeroGPU space. "
        "No auth required — safe for monitoring probes."
    ),
    operation_id="ai_health",
    auth=None,  # Public endpoint — monitoring-safe
)
async def get_ai_health(request) -> dict:
    """GET /api/v1/ninja/ai/health/"""
    from asgiref.sync import sync_to_async
    from django.utils import timezone
    from django.conf import settings
    import httpx

    @sync_to_async
    def check_health():
        results = {
            "ollama_available": False,
            "siglip_available": False,
            "pgvector_ready":   False,
            "mediapipe_ready":  False,
            "ai_engine_url":    "",
            "ai_engine_status": "unknown",
        }

        # ── 1. Check Ollama LLM (local/remote LLM — runs on API gateway) ────────
        try:
            from apps.ai.engines.llm_engine import OllamaLLMEngine
            engine = OllamaLLMEngine()
            results["ollama_available"] = engine.is_available()
        except Exception:
            pass

        # ── 2. Check pgvector (ProductEmbedding table + extension) ─────────────
        try:
            from apps.ai.models.product_embedding import ProductEmbedding
            ProductEmbedding.objects.count()
            results["pgvector_ready"] = True
        except Exception:
            pass

        # ── 3. Check AI Engine ZeroGPU Space (SigLIP + MediaPipe live there) ──
        # The AI Engine is a separate HF ZeroGPU Gradio space. We call its
        # health endpoint to get the real SigLIP / MediaPipe availability.
        ai_engine_url = getattr(
            settings, "AI_ENGINE_URL",
            "https://fashionistar-fashionistar-ai-engine.hf.space"
        )
        results["ai_engine_url"] = ai_engine_url

        try:
            import requests as _req
            resp = _req.get(
                f"{ai_engine_url}/api/predict",
                json={"data": []},
                headers={"Content-Type": "application/json"},
                timeout=8,
            )
            # If the space is running and serving, try the dedicated health fn
            health_resp = _req.post(
                f"{ai_engine_url}/run/health_check",
                json={"data": []},
                timeout=8,
            )
            if health_resp.status_code == 200:
                payload = health_resp.json().get("data", [{}])
                if payload and isinstance(payload[0], dict):
                    engine_health = payload[0]
                    models = engine_health.get("models", {})
                    results["siglip_available"] = models.get("siglip", False)
                    results["mediapipe_ready"]  = models.get("mediapipe", False)
                    results["ai_engine_status"] = "ok"
                else:
                    # Space is up but health fn not ready (cold start)
                    results["ai_engine_status"] = "cold_starting"
            else:
                results["ai_engine_status"] = f"http_{health_resp.status_code}"
        except Exception as exc:
            logger = __import__("logging").getLogger(__name__)
            logger.warning(f"AI Engine space unreachable: {exc}")
            results["ai_engine_status"] = "unreachable"

        return results

    checks = await check_health()
    # Determine overall status:
    # - healthy  = pgvector + at least one AI model up
    # - degraded = partial services
    # - unavailable = nothing works
    pgvector_ok = checks["pgvector_ready"]
    ai_models_ok = checks["siglip_available"] or checks["mediapipe_ready"]
    all_ok = pgvector_ok and ai_models_ok and checks["ollama_available"]
    any_ok = any([pgvector_ok, ai_models_ok])

    return {
        "status":           "healthy" if all_ok else ("degraded" if any_ok else "unavailable"),
        "checked_at":       timezone.now().isoformat(),
        **checks,
    }

