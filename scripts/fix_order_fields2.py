"""Fix remaining date__year and Sum('total') refs in analytics_views.py"""

fpath = r"apps\vendor\apis\sync\analytics_views.py"
with open(fpath, "r", encoding="utf-8") as f:
    content = f.read()

original = content

# Fix 1: date__year  → created_at__year
content = content.replace(
    "                date__year=last_month_cutoff.year,",
    "                created_at__year=last_month_cutoff.year,"
)

# Fix 2: Sum("total") in earning tracker → Sum("total_amount")
content = content.replace(
    '.aggregate(total=Sum("total"))',
    '.aggregate(total=Sum("total_amount"))'
)

# Fix 3: Remaining "total", in values() → "total_amount",
content = content.replace(
    '"total",\n',
    '"total_amount",\n'
)

# Fix 4: "payment_status", → "status", in values()
content = content.replace(
    '"payment_status",\n',
    '"status",\n'
)

# Fix 5: "order_status", → "status", in values()
content = content.replace(
    '"order_status",\n',
    '"status",\n'
)

# Fix 6: "buyer__email", → "user__email",
content = content.replace(
    '"buyer__email",',
    '"user__email",'
)

if content != original:
    with open(fpath, "w", encoding="utf-8") as f:
        f.write(content)
    print("FIXED")
else:
    print("No changes")
