# apps/analytics/workflows/vendor_performance.py
"""
VendorPerformanceWorkflow — analyze a single vendor's performance over a window.

Output: dict snapshot cached at `analytics:report:vendor:{vendor_id}`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)


class VendorPerformanceWorkflow:
    """Workflow for single-vendor performance analytics."""

    workflow_type = "vendor_performance"
    model_version = "vendor-performance-1.0"

    def execute(self, input_data: dict) -> dict:
        """Run the vendor performance analysis pipeline."""
        from apps.ai.workflows.base import BaseWorkflow

        base = BaseWorkflow()
        base.workflow_type = self.workflow_type
        base.model_version = self.model_version

        vendor_id = int(input_data["vendor_id"])
        days = int(input_data.get("days", 30))

        exec_id = base.start_execution(
            input_snapshot={"vendor_id": vendor_id, "days": days},
        )

        try:
            from apps.ai.database.access_layer import FashionistarDatabaseLayer

            db = FashionistarDatabaseLayer()
            vendor_stats = db.get_all_vendor_stats() or []
            vendor_data = next(
                (v for v in vendor_stats if v.get("vendor_id") == vendor_id), {}
            )

            report = {
                "vendor_id":   vendor_id,
                "days":        days,
                "total_sales": vendor_data.get("total_sales", 0),
                "gmv":         vendor_data.get("gmv", 0),
                "top_products": vendor_data.get("top_products", []),
                "rating":      vendor_data.get("rating"),
            }

            cache_key = f"analytics:report:vendor:{vendor_id}"
            cache.set(cache_key, json.dumps(report, default=str), timeout=86400)

            base.complete_execution(output_snapshot={"cache_key": cache_key})
            return report

        except Exception as exc:
            logger.exception(
                "[VendorPerformanceWorkflow] FAILED vendor=%s", vendor_id
            )
            base.fail_execution(exc)
            raise
