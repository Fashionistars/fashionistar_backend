# apps/analytics/workflows/product_performance.py
"""
ProductPerformanceWorkflow — analyze a single product's performance over a window.

Output: dict snapshot cached at `analytics:report:product:{product_id}`.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from django.core.cache import cache

logger = logging.getLogger(__name__)


class ProductPerformanceWorkflow:
    """Workflow for single-product performance analytics."""

    workflow_type = "product_performance"
    model_version = "product-performance-1.0"

    def execute(self, input_data: dict) -> dict:
        """Run the product performance analysis pipeline."""
        from apps.ai.workflows.base import BaseWorkflow

        base = BaseWorkflow()
        base.workflow_type = self.workflow_type
        base.model_version = self.model_version

        product_id = int(input_data["product_id"])
        days = int(input_data.get("days", 30))

        exec_id = base.start_execution(
            input_snapshot={"product_id": product_id, "days": days},
        )

        try:
            from apps.ai.database.access_layer import FashionistarDatabaseLayer

            db = FashionistarDatabaseLayer()
            product_data = db.get_product_full(product_id) or {}

            report = {
                "product_id":  product_id,
                "days":        days,
                "name":        product_data.get("name"),
                "category":    product_data.get("category"),
                "total_views": product_data.get("view_count", 0),
                "total_sales": product_data.get("sales_count", 0),
                "rating":      product_data.get("average_rating"),
                "stock":       product_data.get("stock_quantity"),
            }

            cache_key = f"analytics:report:product:{product_id}"
            cache.set(cache_key, json.dumps(report, default=str), timeout=43200)

            base.complete_execution(output_snapshot={"cache_key": cache_key})
            return report

        except Exception as exc:
            logger.exception(
                "[ProductPerformanceWorkflow] FAILED product=%s", product_id
            )
            base.fail_execution(exc)
            raise
