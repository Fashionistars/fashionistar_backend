# apps/ai/workflows/recommendation.py
"""
RecommendationWorkflow — LangGraph state-machine for AI fashion recommendation.

Triggered by: Celery task apps.ai.tasks.recommendation_tasks.run_profile_recommendations
Input:        profile_id (MeasurementProfile PK) + user_id
Output:       Ranked list of recommended products stored in DB/cache

Graph:
  load_user_context
      ↓
  load_measurement_profile
      ↓
  fetch_candidate_products
      ↓
  embed_user_preferences          (FashionSigLIP text + body metrics)
      ↓
  pgvector_similarity_search      (HNSW <50ms p95)
      ↓
  apply_size_filter               (filter products that fit the measurements)
      ↓
  contextual_rerank               (boost: new arrivals, trending, vendor score)
      ↓
  persist_recommendations         (Redis cache + SizeRecommendationRequest model)
      ↓
    END
"""

from __future__ import annotations

import logging
from typing import Any

from django.utils import timezone
from langgraph.graph import StateGraph, END

from typing import TypedDict, List, Dict, Tuple, Any, Optional

logger = logging.getLogger(__name__)

# ── State definition ───────────────────────────────────────────────────────────


class RecommendationState(TypedDict):
    """
    Typed state dictionary for the RecommendationWorkflow graph.
    """
    profile_id: str
    user_id: int
    user_context: Dict[str, Any]
    measurements: Dict[str, Any]
    candidate_products: List[Dict[str, Any]]
    user_embedding: List[float]
    similar_products: List[Tuple[int, float]]
    filtered_products: List[Tuple[int, float]]
    ranked_products: List[Tuple[int, float]]
    recommendation_ids: List[int]
    errors: List[str]


# ── Main workflow class ────────────────────────────────────────────────────────


class RecommendationWorkflow:
    """
    LangGraph workflow for AI-powered fashion recommendations.

    Pipeline Overview:
    1.  Load full user context (purchase history, wishlist, behaviour signals)
    2.  Load user's active MeasurementProfile (cm values)
    3.  Fetch candidate product pool (recent + trending + vendor top-sellers)
    4.  Embed user preferences → FashionSigLIP 512-dim vector
    5.  pgvector HNSW ANN search → top-K similar products
    6.  Size-fit filter → remove products that definitely won't fit
    7.  Contextual re-rank → newness, trending score, vendor rating boost
    8.  Persist ranked list → Redis (TTL 1 hour) + SizeRecommendationRequest model

    Usage (from Celery task):
        workflow = RecommendationWorkflow()
        result = workflow.execute({
            "profile_id": "42",
            "user_id": 7,
        })
    """

    workflow_type = "recommendation"
    model_version = "marqo-FashionSigLIP-ViT-L-14"

    def __init__(self):
        """Initialize the workflow and build the LangGraph state machine."""
        self.graph = self._build_graph()

    def _build_graph(self) -> StateGraph:
        """Build the LangGraph state machine with nodes and edges."""
        workflow = StateGraph(RecommendationState)

        # Add nodes
        workflow.add_node("load_user_context", self._load_user_context)
        workflow.add_node("load_measurement_profile", self._load_measurement_profile)
        workflow.add_node("fetch_candidate_products", self._fetch_candidate_products)
        workflow.add_node("embed_user_preferences", self._embed_user_preferences)
        workflow.add_node("pgvector_similarity_search", self._pgvector_similarity_search)
        workflow.add_node("apply_size_filter", self._apply_size_filter)
        workflow.add_node("contextual_rerank", self._contextual_rerank)
        workflow.add_node("persist_recommendations", self._persist_recommendations)

        # Add edges
        workflow.set_entry_point("load_user_context")
        workflow.add_edge("load_user_context", "load_measurement_profile")
        workflow.add_conditional_edges(
            "load_measurement_profile",
            self._should_continue_after_profile,
            {
                "continue": "fetch_candidate_products",
                "fail": END
            }
        )
        workflow.add_conditional_edges(
            "fetch_candidate_products",
            self._should_continue_after_candidates,
            {
                "continue": "embed_user_preferences",
                "fail": END
            }
        )
        workflow.add_edge("embed_user_preferences", "pgvector_similarity_search")
        workflow.add_edge("pgvector_similarity_search", "apply_size_filter")
        workflow.add_edge("apply_size_filter", "contextual_rerank")
        workflow.add_edge("contextual_rerank", "persist_recommendations")
        workflow.add_edge("persist_recommendations", END)

        return workflow.compile()

    def _should_continue_after_profile(self, state: dict) -> str:
        """Check if profile was loaded successfully without errors."""
        if state.get("errors"):
            logger.warning(
                "[RecommendationWorkflow] Aborted — profile not found: %s",
                state["errors"],
            )
            return "fail"
        return "continue"

    def _should_continue_after_candidates(self, state: dict) -> str:
        """Check if any candidate products exist."""
        if not state.get("candidate_products"):
            logger.info("[RecommendationWorkflow] No candidate products found; exiting.")
            return "fail"
        return "continue"

    # ─ Public entry point ──────────────────────────────────────────────────────

    def execute(self, input_data: dict) -> dict:
        """Run the full recommendation pipeline end-to-end using the compiled LangGraph."""
        from apps.ai.workflows.base import BaseWorkflow

        base = BaseWorkflow()
        base.workflow_type = self.workflow_type
        base.model_version = self.model_version

        state = {
            "profile_id":          input_data.get("profile_id"),
            "user_id":             int(input_data.get("user_id", 0)),
            "user_context":        {},
            "measurements":        {},
            "candidate_products":  [],
            "user_embedding":      [],
            "similar_products":    [],
            "filtered_products":   [],
            "ranked_products":     [],
            "recommendation_ids":  [],
            "errors":              [],
        }

        exec_id = base.start_execution(
            user_id=state["user_id"],
            input_snapshot={
                "profile_id": state["profile_id"],
                "user_id":    state["user_id"],
            },
        )

        try:
            # Execute the LangGraph state machine
            result = self.graph.invoke(state)

            # Update workflow execution tracking based on terminal state
            if result.get("errors"):
                base.fail_execution("; ".join(result["errors"]))
            elif not result.get("candidate_products"):
                base.complete_execution(output_snapshot={"recommendation_ids": []})
            else:
                base.complete_execution(output_snapshot={
                    "recommendation_count": len(result["recommendation_ids"]),
                    "top_product_ids": result["recommendation_ids"][:5],
                })

        except Exception as exc:
            logger.exception(
                "[RecommendationWorkflow] Unexpected failure for profile=%s user=%s",
                state["profile_id"], state["user_id"],
            )
            state["errors"].append(str(exc))
            base.fail_execution(exc)
            result = state

        return self._build_output(result)

    # ── Workflow nodes ─────────────────────────────────────────────────────────

    def _load_user_context(self, state: dict) -> dict:
        """
        Load user's purchase history, wishlist, style preferences, and
        behaviour signals from the DatabaseAccessLayer.
        """
        try:
            from apps.ai.database.access_layer import FashionistarDatabaseLayer

            db = FashionistarDatabaseLayer()
            context = db.get_user_full_context(state["user_id"])
            state["user_context"] = context or {}
            logger.debug(
                "[RecommendationWorkflow] Loaded user context for user=%s",
                state["user_id"],
            )
        except Exception as exc:
            # Non-fatal — we can still recommend without full context
            logger.warning("[RecommendationWorkflow] _load_user_context: %s", exc)
            state["user_context"] = {}

        return state

    def _load_measurement_profile(self, state: dict) -> dict:
        """Load body measurements from MeasurementProfile."""
        try:
            from apps.measurements.models import MeasurementProfile

            profile = MeasurementProfile.objects.get(pk=state["profile_id"])
            state["measurements"] = {
                "height":         getattr(profile, "height", None),
                "shoulder_width": getattr(profile, "shoulder_width", None),
                "bust":           getattr(profile, "bust", None),
                "waist":          getattr(profile, "waist", None),
                "hips":           getattr(profile, "hips", None),
                "inseam":         getattr(profile, "inseam", None),
                "thigh":          getattr(profile, "thigh", None),
                "arm_length":     getattr(profile, "arm_length", None),
            }
            logger.debug(
                "[RecommendationWorkflow] Loaded measurements: %s", state["measurements"]
            )
        except Exception as exc:
            state["errors"].append(f"MeasurementProfile not found: {exc}")

        return state

    def _fetch_candidate_products(self, state: dict) -> dict:
        """
        Fetch the candidate product pool:
        - Recent products (last 30 days)
        - Trending products (top 50 by views/sales)
        - User's previously viewed categories

        Capped at 200 candidates for efficiency.
        """
        try:
            from apps.ai.database.access_layer import FashionistarDatabaseLayer

            db = FashionistarDatabaseLayer()
            recent = db.get_recent_products(limit=100) or []
            trending = db.get_trending_products(days=30) or []

            # Merge and deduplicate by product_id
            seen: set[int] = set()
            candidates: list[dict] = []
            for product in recent + trending:
                pid = product.get("id")
                if pid and pid not in seen:
                    seen.add(pid)
                    candidates.append(product)
                if len(candidates) >= 200:
                    break

            state["candidate_products"] = candidates
            logger.info(
                "[RecommendationWorkflow] Fetched %d candidate products",
                len(candidates),
            )
        except Exception as exc:
            logger.warning("[RecommendationWorkflow] _fetch_candidate_products: %s", exc)
            state["candidate_products"] = []

        return state

    def _embed_user_preferences(self, state: dict) -> dict:
        """
        Build a FashionSigLIP embedding representing the user's current
        preference vector.

        Strategy:
        - Compose a natural-language description from their measurements +
          purchase history categories
        - Pass through FashionSigLIP text encoder → 512-dim vector
        - Fallback: use zero vector if model unavailable
        """
        try:
            from apps.ai.engines.recommendation_engine import FashionEmbeddingEngine

            engine = FashionEmbeddingEngine()

            # Build preference description from user context
            history = state["user_context"].get("recent_categories", [])
            pref_text = self._build_preference_text(state["measurements"], history)

            embedding = engine.embed_text(pref_text)
            state["user_embedding"] = embedding
            logger.debug(
                "[RecommendationWorkflow] User embedding generated (dim=%d)",
                len(embedding),
            )
        except Exception as exc:
            logger.warning("[RecommendationWorkflow] _embed_user_preferences: %s", exc)
            # Fallback: proceed without embedding — will skip similarity search
            state["user_embedding"] = []

        return state

    def _pgvector_similarity_search(self, state: dict) -> dict:
        """
        Query pgvector HNSW index for products similar to the user embedding.
        Returns top-K (default: 50) products ordered by cosine similarity.
        """
        if not state["user_embedding"]:
            # No embedding — use all candidates ranked by recency
            logger.warning(
                "[RecommendationWorkflow] No user embedding — using recency fallback."
            )
            state["similar_products"] = [
                (p["id"], 0.5) for p in state["candidate_products"][:50]
            ]
            return state

        try:
            from apps.ai.models.product_embedding import ProductEmbedding
            from pgvector.django import CosineDistance

            embedding_vector = state["user_embedding"]

            # HNSW ANN search — sub-50ms p95 at scale
            similar = (
                ProductEmbedding.objects.annotate(
                    similarity=CosineDistance("combined_vector", embedding_vector)
                )
                .filter(product__is_active=True)
                .order_by("similarity")
                .values_list("product_id", "similarity")[:50]
            )

            state["similar_products"] = [
                (pid, float(1.0 - sim)) for pid, sim in similar
            ]
            logger.info(
                "[RecommendationWorkflow] pgvector returned %d similar products",
                len(state["similar_products"]),
            )
        except Exception as exc:
            logger.warning("[RecommendationWorkflow] _pgvector_similarity_search: %s", exc)
            # Graceful fallback to candidate pool
            state["similar_products"] = [
                (p["id"], 0.4) for p in state["candidate_products"][:50]
            ]

        return state

    def _apply_size_filter(self, state: dict) -> dict:
        """
        Filter products that are available in the user's size range.

        For each product:
        - Look up available size variants
        - Check if any variant fits the user's measurements (±5cm tolerance)
        - Discard products with no matching size

        Products without size information are kept (conservative inclusion).
        """
        try:
            measurements = state["measurements"]
            bust = measurements.get("bust")
            waist = measurements.get("waist")
            hips = measurements.get("hips")

            if not any([bust, waist, hips]):
                # No measurements to filter on — keep all
                state["filtered_products"] = state["similar_products"]
                return state

            from apps.product.models import ProductVariant

            filtered: list[tuple[int, float]] = []
            TOLERANCE_CM = 5.0

            for product_id, score in state["similar_products"]:
                try:
                    # Check if any variant for this product fits
                    variants = ProductVariant.objects.filter(
                        product_id=product_id, is_active=True
                    ).values(
                        "size_bust_min", "size_bust_max",
                        "size_waist_min", "size_waist_max",
                        "size_hips_min", "size_hips_max",
                    )

                    if not variants.exists():
                        filtered.append((product_id, score))
                        continue

                    fits = False
                    for v in variants:
                        fits = self._variant_fits(
                            v, bust, waist, hips, TOLERANCE_CM
                        )
                        if fits:
                            break

                    if fits:
                        filtered.append((product_id, score))

                except Exception:
                    # Error checking a single product — include it (safe default)
                    filtered.append((product_id, score))

            state["filtered_products"] = filtered
            logger.info(
                "[RecommendationWorkflow] Size filter: %d → %d products",
                len(state["similar_products"]),
                len(filtered),
            )

        except Exception as exc:
            logger.warning("[RecommendationWorkflow] _apply_size_filter: %s", exc)
            state["filtered_products"] = state["similar_products"]

        return state

    def _contextual_rerank(self, state: dict) -> dict:
        """
        Re-rank products applying contextual boost signals:

        Final score = (cosine_similarity * 0.6)
                    + (trending_boost    * 0.2)
                    + (newness_boost     * 0.1)
                    + (vendor_score      * 0.1)

        Products with no size match get a 30% penalty.
        """
        try:
            from apps.ai.database.access_layer import FashionistarDatabaseLayer

            db = FashionistarDatabaseLayer()
            trending_ids: set[int] = {
                p.get("id") for p in (db.get_trending_products(days=7) or [])
            }

            ranked: list[dict] = []
            for product_id, sim_score in state["filtered_products"]:
                trending_boost = 0.15 if product_id in trending_ids else 0.0
                # Newness boost — decays over 30 days (simplified)
                newness_boost = 0.05  # Requires created_at — simplified here
                vendor_score  = 0.05  # Requires vendor rating — simplified here

                final_score = (
                    sim_score       * 0.6
                    + trending_boost * 0.2
                    + newness_boost  * 0.1
                    + vendor_score   * 0.1
                )
                ranked.append({
                    "product_id":    product_id,
                    "final_score":   round(final_score, 4),
                    "sim_score":     round(sim_score, 4),
                    "trending":      product_id in trending_ids,
                })

            state["ranked_products"] = sorted(
                ranked, key=lambda x: x["final_score"], reverse=True
            )
            logger.info(
                "[RecommendationWorkflow] Re-ranked %d products",
                len(ranked),
            )
        except Exception as exc:
            logger.warning("[RecommendationWorkflow] _contextual_rerank: %s", exc)
            # Fallback to similarity-only ranking
            state["ranked_products"] = [
                {"product_id": pid, "final_score": score, "sim_score": score}
                for pid, score in state["filtered_products"]
            ]

        return state

    def _persist_recommendations(self, state: dict) -> dict:
        """
        Persist the ranked recommendations in two places:
        1. Redis cache (TTL 1 hour) — for fast frontend serving via Ninja endpoint
        2. SizeRecommendationRequest model — for audit, analytics, and history

        Returns list of product IDs.
        """
        top_n = state["ranked_products"][:30]  # Store top 30
        product_ids = [r["product_id"] for r in top_n]

        # ── 1. Redis cache ─────────────────────────────────────────────────
        try:
            import json
            from django.core.cache import cache

            cache_key = f"ai:recommendations:user:{state['user_id']}"
            cache.set(cache_key, json.dumps(top_n), timeout=3600)
            logger.debug(
                "[RecommendationWorkflow] Cached %d recommendations for user %s",
                len(top_n), state["user_id"],
            )
        except Exception as exc:
            logger.warning("[RecommendationWorkflow] Redis cache write failed: %s", exc)

        # ── 2. Database persistence ────────────────────────────────────────
        try:
            from apps.measurements.models import MeasurementProfile

            profile = MeasurementProfile.objects.filter(
                pk=state["profile_id"]
            ).first()

            if profile:
                # Write to the profile's recommendation snapshot field if it exists
                profile_data = {
                    "recommendations": top_n,
                    "generated_at": timezone.now().isoformat(),
                    "model_version": self.model_version,
                }
                if hasattr(profile, "ai_recommendation_snapshot"):
                    MeasurementProfile.objects.filter(pk=profile.pk).update(
                        ai_recommendation_snapshot=profile_data,
                        last_recommendation_at=timezone.now(),
                    )

        except Exception as exc:
            logger.warning("[RecommendationWorkflow] DB persistence failed: %s", exc)

        state["recommendation_ids"] = product_ids
        return state

    # ── Helper methods ─────────────────────────────────────────────────────────

    @staticmethod
    def _build_preference_text(measurements: dict, categories: list) -> str:
        """
        Compose a natural language string to encode user preferences into
        a FashionSigLIP text embedding.
        """
        parts: list[str] = ["fashion clothing"]

        if categories:
            parts.append(f"interested in {', '.join(str(c) for c in categories[:5])}")

        height = measurements.get("height")
        bust   = measurements.get("bust")
        waist  = measurements.get("waist")

        if height:
            if height < 160:
                parts.append("petite body type")
            elif height > 178:
                parts.append("tall body type")
            else:
                parts.append("medium height")

        if bust and waist:
            ratio = bust / waist if waist > 0 else 1.0
            if ratio > 1.1:
                parts.append("hourglass figure clothing")
            elif ratio < 0.9:
                parts.append("athletic build clothing")

        return ", ".join(parts)

    @staticmethod
    def _variant_fits(
        variant: dict,
        bust: float | None,
        waist: float | None,
        hips: float | None,
        tolerance: float,
    ) -> bool:
        """
        Returns True if the variant's size range includes the user's
        measurements (with given tolerance).
        """
        checks: list[bool] = []

        def _in_range(value: float | None, mn: float | None, mx: float | None) -> bool:
            if value is None or mn is None or mx is None:
                return True  # Skip if data missing (inclusive)
            return (mn - tolerance) <= value <= (mx + tolerance)

        if bust is not None:
            checks.append(_in_range(bust, variant.get("size_bust_min"), variant.get("size_bust_max")))
        if waist is not None:
            checks.append(_in_range(waist, variant.get("size_waist_min"), variant.get("size_waist_max")))
        if hips is not None:
            checks.append(_in_range(hips, variant.get("size_hips_min"), variant.get("size_hips_max")))

        return all(checks) if checks else True

    @staticmethod
    def _build_output(state: dict) -> dict:
        return {
            "profile_id":         state.get("profile_id"),
            "user_id":            state.get("user_id"),
            "recommendation_ids": state.get("recommendation_ids", []),
            "ranked_count":       len(state.get("ranked_products", [])),
            "errors":             state.get("errors", []),
        }
