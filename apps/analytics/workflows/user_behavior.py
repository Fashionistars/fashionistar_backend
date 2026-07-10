# apps/analytics/workflows/user_behavior.py
"""
UserBehaviorWorkflow — analyze a single user's behaviour over a lookback window.

Output: dict snapshot cached at `analytics:report:user:{user_id}`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)


class UserBehaviorWorkflow:
    """Workflow for single-user behaviour analytics."""

    workflow_type = "user_behavior"
    model_version = "user-behavior-1.0"

    def execute(self, input_data: dict) -> dict:
        """Run the user behaviour analysis pipeline."""
        from apps.ai.workflows.base import BaseWorkflow

        base = BaseWorkflow()
        base.workflow_type = self.workflow_type
        base.model_version = self.model_version

        user_id = int(input_data["user_id"])
        days = int(input_data.get("days", 30))

        exec_id = base.start_execution(
            input_snapshot={"user_id": user_id, "days": days},
        )

        try:
            from apps.ai.database.access_layer import FashionistarDatabaseLayer

            db = FashionistarDatabaseLayer()
            context    = db.get_user_full_context(user_id) or {}
            orders     = db.get_user_order_history(user_id) or []
            measures   = db.get_user_measurements(user_id) or []

            report = {
                "user_id":               user_id,
                "days":                  days,
                "total_orders":          len(orders),
                "measurement_profiles":  len(measures),
                "has_default_profile":   any(m.get("is_default") for m in measures),
                "purchase_categories":   context.get("recent_categories", []),
                "engagement_signals":    context.get("engagement", {}),
            }

            cache_key = f"analytics:report:user:{user_id}"
            cache.set(cache_key, json.dumps(report, default=str), timeout=86400)

            base.complete_execution(output_snapshot={"cache_key": cache_key})
            return report

        except Exception as exc:
            logger.exception("[UserBehaviorWorkflow] FAILED user=%s", user_id)
            base.fail_execution(exc)
            raise
