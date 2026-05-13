"""
Fix script: Normalize all CartOrder field names across vendor analytics_views.py
Old field names (from an older model design):
  - total          → total_amount
  - payment_status → status  (no such field; use status)
  - order_status   → status  (same unified field)
  - date           → created_at
  - buyer__email   → user__email

Also fix: VendorOrderDetailView object fields and EarningTrackerView filter fields.
"""
import re

fpath = r"apps\vendor\apis\sync\analytics_views.py"

with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

original = content

# 1. In .values() and .filter() calls: field name fixes
#    "total" as ORM field → "total_amount"
content = re.sub(r'"total",\n(\s+)"payment_status",\n(\s+)"order_status",\n(\s+)"date",\n(\s+)"buyer__email",',
                 '"total_amount",\n\\1"status",\n\\2"status",\n\\3"created_at",\n\\4"user__email",',
                 content)

# 2. .filter(payment_status=payment_status) → .filter(status=payment_status)
content = content.replace("qs.filter(payment_status=payment_status)", "qs.filter(status=payment_status)")

# 3. .filter(order_status=order_status) → .filter(status=order_status)
content = content.replace("qs.filter(order_status=order_status)", "qs.filter(status=order_status)")

# 4. .filter(payment_status="paid" → .filter(status__in=["paid","completed",...  
#    For the EarningTrackerView monthly calc
content = content.replace('filter(\n                payment_status="paid",\n                date__month', 
                           'filter(\n                status__in=["payment_confirmed","completed","delivered"],\n                created_at__month')

# 5. VendorOrderDetailView object return (individual field access)
content = content.replace('"total": str(order.total),', '"total": str(order.total_amount),')
content = content.replace('"payment_status": order.payment_status,', '"status": order.status,')
content = content.replace('"order_status": order.order_status,', '"status_label": order.status,')
content = content.replace('"date": order.date,', '"date": order.created_at,')
content = content.replace('"buyer_email": getattr(order.buyer, "email", ""),', '"buyer_email": getattr(order.user, "email", ""),')

# 6. date__year / date__month in earning tracker filter
content = content.replace("date__month=last_month_cutoff.month,\n                date__year=last_month_cutoff.year,",
                           "created_at__month=last_month_cutoff.month,\n                created_at__year=last_month_cutoff.year,")

# 7. .get_todays_sales() etc use 'total' internally — check model method
# Those are model methods, not view queries, skip.

# 8. Summary analytics: profile.total vs profile.total_revenue etc. Those reference
#    denormalized model attrs (not ORM queries), skip.

# 9. get_pending_payouts uses 'total_amount' already — check vendor_profile model
# (Already fixed in model layer)

if content != original:
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"FIXED: {fpath}")
else:
    print(f"No changes: {fpath}")

print("Done.")
