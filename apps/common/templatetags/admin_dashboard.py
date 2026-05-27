from __future__ import annotations

import json
from collections import defaultdict
from datetime import timedelta

from django import template
from django.db.models import Count, Sum
from django.utils import timezone

from apps.kyc.models import KycStatus, KycSubmission
from apps.order.models import Order
from apps.product.models import Product
from apps.vendor.models import VendorProfile

register = template.Library()


@register.simple_tag
def fashionistar_admin_dashboard_metrics() -> str:
    """
    JSON payload for the custom admin dashboard charts/cards.
    """

    today = timezone.now().date()
    start_date = today - timedelta(days=6)

    revenue_map: dict[str, float] = defaultdict(float)
    revenue_rows = (
        Order.objects.filter(
            created_at__date__gte=start_date,
            paid_at__isnull=False,
        )
        .values("created_at__date")
        .annotate(total=Sum("total_amount"))
        .order_by("created_at__date")
    )
    for row in revenue_rows:
        revenue_map[row["created_at__date"].isoformat()] = float(row["total"] or 0)

    vendor_map: dict[str, int] = defaultdict(int)
    vendor_rows = (
        VendorProfile.objects.filter(created_at__date__gte=start_date)
        .values("created_at__date")
        .annotate(total=Count("id"))
        .order_by("created_at__date")
    )
    for row in vendor_rows:
        vendor_map[row["created_at__date"].isoformat()] = row["total"]

    chart_labels = [
        (start_date + timedelta(days=offset)).isoformat() for offset in range(7)
    ]
    daily_revenue = [revenue_map[label] for label in chart_labels]
    new_vendors = [vendor_map[label] for label in chart_labels]

    low_stock_rows = list(
        Product.objects.filter(stock_qty__lte=5, is_deleted=False)
        .select_related("vendor")
        .order_by("stock_qty", "title")[:8]
    )

    pending_kyc = KycSubmission.objects.filter(status=KycStatus.PENDING).count()

    payload = {
        "chart_labels": chart_labels,
        "daily_revenue": daily_revenue,
        "new_vendors": new_vendors,
        "low_stock_count": len(low_stock_rows),
        "low_stock_items": [
            {
                "title": product.title,
                "stock_qty": product.stock_qty,
                "vendor": getattr(product.vendor, "business_name", "")
                or getattr(product.vendor, "store_name", ""),
            }
            for product in low_stock_rows
        ],
        "kyc_pending_count": pending_kyc,
    }
    return json.dumps(payload)
