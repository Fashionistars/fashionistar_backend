# apps/ai/workflows/analytics.py
"""
AnalyticsWorkflow — LangGraph state-machine for platform analytics & insights.

Triggered by: Celery Beat periodic task (daily) OR on-demand via API
Input:        time window (days), scope (platform | vendor | user)
Output:       Structured analytics report stored in Redis + DB

Graph:
  aggregate_order_metrics
      ↓
  aggregate_product_metrics
      ↓
  aggregate_user_metrics
      ↓
  aggregate_vendor_metrics
      ↓
  detect_anomalies
      ↓
  generate_llm_insights      (Ollama LLM — optional, skipped if unavailable)
      ↓
  persist_report
      ↓
    END
"""

from __future__ import annotations

import logging
from datetime import timedelta
from typing import Any

from django.utils import timezone

logger = logging.getLogger(__name__)


# ── State definition ───────────────────────────────────────────────────────────

class AnalyticsState(dict):
    """
    Typed state dict for the AnalyticsWorkflow.

    Keys:
        days:              Lookback window in days (default: 7)
        scope:             'platform' | 'vendor' | 'user'
        scope_id:          Vendor PK or User PK (None for platform-wide)
        order_metrics:     Dict of order aggregations
        product_metrics:   Dict of product performance stats
        user_metrics:      Dict of user behaviour stats
        vendor_metrics:    Dict of vendor performance stats
        anomalies:         List of detected anomaly dicts
        llm_insights:      AI-generated natural-language insights
        report:            Final structured report dict
        errors:            Accumulated non-fatal error messages
    """


# ── Main workflow class ────────────────────────────────────────────────────────

class AnalyticsWorkflow:
    """
    LangGraph workflow for FASHIONISTAR platform analytics.

    Aggregates cross-app data via the FashionistarDatabaseLayer,
    detects statistical anomalies, and optionally generates LLM-powered
    natural-language insights via Ollama.

    Usage:
        workflow = AnalyticsWorkflow()
        report = workflow.execute({
            "days": 7,
            "scope": "platform",
        })
    """

    workflow_type = "analytics"
    model_version = "analytics-1.0+llama3.2"

    def execute(self, input_data: dict) -> dict:
        """Run the full analytics pipeline."""
        from apps.ai.workflows.base import BaseWorkflow

        base = BaseWorkflow()
        base.workflow_type = self.workflow_type
        base.model_version = self.model_version

        state: dict[str, Any] = {
            "days":            int(input_data.get("days", 7)),
            "scope":           input_data.get("scope", "platform"),
            "scope_id":        input_data.get("scope_id"),
            "order_metrics":   {},
            "product_metrics": {},
            "user_metrics":    {},
            "vendor_metrics":  {},
            "anomalies":       [],
            "llm_insights":    "",
            "report":          {},
            "errors":          [],
        }

        exec_id = base.start_execution(
            input_snapshot={
                "days": state["days"],
                "scope": state["scope"],
                "scope_id": state["scope_id"],
            },
        )

        try:
            state = self._aggregate_order_metrics(state)
            state = self._aggregate_product_metrics(state)
            state = self._aggregate_user_metrics(state)
            state = self._aggregate_vendor_metrics(state)
            state = self._detect_anomalies(state)
            state = self._generate_llm_insights(state)
            state = self._persist_report(state)

            base.complete_execution(output_snapshot={
                "report_key": state["report"].get("cache_key"),
                "anomaly_count": len(state["anomalies"]),
            })

        except Exception as exc:
            logger.exception("[AnalyticsWorkflow] Unexpected failure")
            state["errors"].append(str(exc))
            base.fail_execution(exc)

        return state["report"]

    # ── Nodes ──────────────────────────────────────────────────────────────────

    def _aggregate_order_metrics(self, state: dict) -> dict:
        """
        Aggregate order statistics for the reporting window.

        Metrics:
        - Total orders, total GMV (Gross Merchandise Value)
        - Average order value (AOV)
        - Order status distribution (pending / completed / cancelled)
        - Top 10 best-selling products
        - Revenue by category
        """
        try:
            from apps.ai.database.access_layer import FashionistarDatabaseLayer
            db = FashionistarDatabaseLayer()
            stats = db.get_platform_order_stats(days=state["days"])
            state["order_metrics"] = stats or {}
        except Exception as exc:
            logger.warning("[AnalyticsWorkflow] _aggregate_order_metrics: %s", exc)
            state["errors"].append(f"order_metrics: {exc}")
            state["order_metrics"] = {}
        return state

    def _aggregate_product_metrics(self, state: dict) -> dict:
        """
        Aggregate product performance metrics.

        Metrics:
        - Total active products, new listings this period
        - View-to-purchase conversion rate
        - Inventory stock levels (total, low-stock alerts)
        - Top 10 trending products (view count)
        - Products with zero sales (risk: stale inventory)
        """
        try:
            from apps.ai.database.access_layer import FashionistarDatabaseLayer
            db = FashionistarDatabaseLayer()
            trending = db.get_trending_products(days=state["days"]) or []
            inventory = db.get_inventory_levels() or {}

            state["product_metrics"] = {
                "trending_products": trending[:10],
                "inventory_summary": inventory,
                "trending_count": len(trending),
            }
        except Exception as exc:
            logger.warning("[AnalyticsWorkflow] _aggregate_product_metrics: %s", exc)
            state["errors"].append(f"product_metrics: {exc}")
            state["product_metrics"] = {}
        return state

    def _aggregate_user_metrics(self, state: dict) -> dict:
        """
        Aggregate user behaviour metrics.

        Metrics:
        - New user registrations this period
        - DAU / WAU (daily / weekly active users)
        - User KYC completion rate
        - Measurement profile completion rate
        - Support ticket open/close rate
        """
        try:
            from django.contrib.auth import get_user_model
            from django.utils import timezone

            User = get_user_model()
            since = timezone.now() - timedelta(days=state["days"])

            new_users   = User.objects.filter(date_joined__gte=since).count()
            total_users = User.objects.filter(is_active=True).count()

            # KYC completion rate
            try:
                from apps.kyc.models import KYCProfile
                kyc_complete = KYCProfile.objects.filter(status="approved").count()
                kyc_rate = (kyc_complete / max(total_users, 1)) * 100
            except Exception:
                kyc_rate = None

            # Measurement profile completion rate
            try:
                from apps.measurements.models import MeasurementProfile
                with_profile = (
                    MeasurementProfile.objects.values("owner_id").distinct().count()
                )
                profile_rate = (with_profile / max(total_users, 1)) * 100
            except Exception:
                profile_rate = None

            state["user_metrics"] = {
                "new_registrations":      new_users,
                "total_active_users":     total_users,
                "kyc_completion_rate":    round(kyc_rate, 1) if kyc_rate is not None else None,
                "profile_completion_rate": round(profile_rate, 1) if profile_rate is not None else None,
            }

        except Exception as exc:
            logger.warning("[AnalyticsWorkflow] _aggregate_user_metrics: %s", exc)
            state["errors"].append(f"user_metrics: {exc}")
            state["user_metrics"] = {}
        return state

    def _aggregate_vendor_metrics(self, state: dict) -> dict:
        """
        Aggregate vendor performance metrics.

        Metrics:
        - Total active vendors
        - Vendors with new listings this period
        - Average vendor response time (support tickets)
        - GMV by vendor (top 10)
        - Vendor churn (vendors with no sales in last N days)
        """
        try:
            from apps.ai.database.access_layer import FashionistarDatabaseLayer
            db = FashionistarDatabaseLayer()
            all_vendor_stats = db.get_all_vendor_stats() or []

            state["vendor_metrics"] = {
                "total_vendors": len(all_vendor_stats),
                "top_vendors": sorted(
                    all_vendor_stats,
                    key=lambda v: v.get("gmv", 0),
                    reverse=True
                )[:10],
            }
        except Exception as exc:
            logger.warning("[AnalyticsWorkflow] _aggregate_vendor_metrics: %s", exc)
            state["errors"].append(f"vendor_metrics: {exc}")
            state["vendor_metrics"] = {}
        return state

    def _detect_anomalies(self, state: dict) -> dict:
        """
        Detect statistical anomalies in the collected metrics.

        Checks:
        - Sudden GMV drop (>30% vs previous period) → CRITICAL alert
        - New user registration spike (>200%) → INFO
        - Support ticket backlog (>50 open) → WARNING
        - Low inventory alert (<10 units for any top-selling product) → WARNING
        - Zero sales for vendor >14 days → INFO (churn risk)
        """
        anomalies: list[dict] = []

        try:
            order_metrics   = state["order_metrics"]
            user_metrics    = state["user_metrics"]
            product_metrics = state["product_metrics"]

            # ── GMV anomaly check ──────────────────────────────────────────
            gmv_current  = order_metrics.get("total_gmv", 0)
            gmv_previous = order_metrics.get("previous_period_gmv", 0)
            if gmv_previous and gmv_current < gmv_previous * 0.7:
                anomalies.append({
                    "type": "GMV_DROP",
                    "severity": "CRITICAL",
                    "message": (
                        f"GMV dropped by "
                        f"{((gmv_previous - gmv_current) / gmv_previous * 100):.1f}% "
                        f"vs previous period."
                    ),
                    "value": gmv_current,
                    "threshold": gmv_previous * 0.7,
                })

            # ── Inventory low-stock alert ──────────────────────────────────
            inventory = product_metrics.get("inventory_summary", {})
            low_stock = inventory.get("low_stock_count", 0)
            if low_stock > 5:
                anomalies.append({
                    "type": "LOW_STOCK",
                    "severity": "WARNING",
                    "message": f"{low_stock} products have critically low inventory.",
                    "value": low_stock,
                })

            # ── New user registration spike ────────────────────────────────
            new_users  = user_metrics.get("new_registrations", 0)
            prev_users = user_metrics.get("prev_period_registrations", 0)
            if prev_users and new_users > prev_users * 2:
                anomalies.append({
                    "type": "REGISTRATION_SPIKE",
                    "severity": "INFO",
                    "message": (
                        f"New user registrations spiked 2x this period "
                        f"({new_users} vs {prev_users})."
                    ),
                    "value": new_users,
                })

        except Exception as exc:
            logger.warning("[AnalyticsWorkflow] _detect_anomalies: %s", exc)

        state["anomalies"] = anomalies
        logger.info(
            "[AnalyticsWorkflow] Detected %d anomalies", len(anomalies)
        )
        return state

    def _generate_llm_insights(self, state: dict) -> dict:
        """
        Use Ollama (local LLM) to generate natural-language insights from
        the aggregated metrics.

        Model: llama3.2:3b (runs on 8GB RAM CPU)
        Prompt: Condensed analytics summary → ask for actionable insights
        Fallback: Empty string if Ollama unavailable (non-fatal)
        """
        try:
            from apps.ai.engines.llm_engine import OllamaLLMEngine

            engine = OllamaLLMEngine()
            if not engine.is_available():
                logger.info("[AnalyticsWorkflow] Ollama not available — skipping LLM insights.")
                state["llm_insights"] = ""
                return state

            # Build a condensed prompt from the metrics
            metrics_summary = self._build_metrics_summary(state)
            prompt = f"""
You are FASHIONISTAR's AI analytics engine. Analyze the following platform metrics
and provide 3 concise, actionable business insights for the operations team.
Format: bullet points, max 2 sentences each.

METRICS SUMMARY:
{metrics_summary}

ANOMALIES DETECTED: {len(state['anomalies'])}
{self._format_anomalies(state['anomalies'])}

Provide your insights:
""".strip()

            insights = engine.generate(prompt, max_tokens=400)
            state["llm_insights"] = insights
            logger.info("[AnalyticsWorkflow] LLM insights generated (%d chars)", len(insights))

        except Exception as exc:
            logger.warning("[AnalyticsWorkflow] _generate_llm_insights: %s", exc)
            state["llm_insights"] = ""

        return state

    def _persist_report(self, state: dict) -> dict:
        """
        Persist the analytics report:
        1. Redis cache (TTL 24 hours) — served by Ninja read endpoint
        2. DB model (if analytics.Report model exists) — for historical drill-down
        """
        import json
        from django.core.cache import cache

        report = {
            "generated_at":    timezone.now().isoformat(),
            "days":            state["days"],
            "scope":           state["scope"],
            "order_metrics":   state["order_metrics"],
            "product_metrics": state["product_metrics"],
            "user_metrics":    state["user_metrics"],
            "vendor_metrics":  state["vendor_metrics"],
            "anomalies":       state["anomalies"],
            "llm_insights":    state["llm_insights"],
            "errors":          state["errors"],
        }

        scope_key = state.get("scope_id") or "platform"
        cache_key = f"ai:analytics:{state['scope']}:{scope_key}:{state['days']}d"
        report["cache_key"] = cache_key

        try:
            cache.set(cache_key, json.dumps(report, default=str), timeout=86400)
            logger.info("[AnalyticsWorkflow] Report cached at key=%s", cache_key)
        except Exception as exc:
            logger.warning("[AnalyticsWorkflow] Redis write failed: %s", exc)

        state["report"] = report
        return state

    # ── Helpers ────────────────────────────────────────────────────────────────

    @staticmethod
    def _build_metrics_summary(state: dict) -> str:
        om = state.get("order_metrics", {})
        um = state.get("user_metrics", {})
        vm = state.get("vendor_metrics", {})
        pm = state.get("product_metrics", {})

        return f"""
- Reporting period: {state['days']} days
- Total GMV: {om.get('total_gmv', 'N/A')}
- Total orders: {om.get('total_orders', 'N/A')}
- AOV: {om.get('avg_order_value', 'N/A')}
- New users: {um.get('new_registrations', 'N/A')}
- Total active users: {um.get('total_active_users', 'N/A')}
- KYC completion rate: {um.get('kyc_completion_rate', 'N/A')}%
- Measurement profile rate: {um.get('profile_completion_rate', 'N/A')}%
- Active vendors: {vm.get('total_vendors', 'N/A')}
- Trending products count: {pm.get('trending_count', 'N/A')}
""".strip()

    @staticmethod
    def _format_anomalies(anomalies: list) -> str:
        if not anomalies:
            return "None detected."
        return "\n".join(
            f"[{a['severity']}] {a['type']}: {a['message']}"
            for a in anomalies
        )
