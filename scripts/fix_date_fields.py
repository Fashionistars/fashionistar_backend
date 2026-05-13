"""
Fix script: Replace all product-query 'date' field refs with 'created_at'
in analytics_views.py and product_views.py.
"""
import re

files = [
    r"apps\vendor\apis\sync\analytics_views.py",
    r"apps\vendor\apis\sync\product_views.py",
]

for fpath in files:
    try:
        with open(fpath, "r", encoding="utf-8") as f:
            content = f.read()
        
        original = content
        
        # Pattern 1: "date", in values() calls → "created_at",
        # Only replace in product-field context (between "status" and closing paren)
        # Simple approach: replace all standalone "date" in values() as field name
        # The field "date" appears in order models too — be careful
        # We replace only when it's in a .values("id", "title", ... "date") context
        # Regex: "date", followed by whitespace then ) — i.e. it's the LAST item
        content = re.sub(
            r'(\s+)"date",\n(\s+\))',
            r'\1"created_at",\n\2',
            content
        )
        
        # Pattern 2: order_by("-date") for products
        content = re.sub(
            r'\.order_by\("-date"\)',
            '.order_by("-created_at")',
            content
        )
        content = re.sub(
            r'\.order_by\("date"\)',
            '.order_by("created_at")',
            content
        )
        
        # Pattern 3: "date" if ordering == "oldest" else "-date"
        content = re.sub(
            r'"date" if ordering == "oldest" else "-date"',
            '"created_at" if ordering == "oldest" else "-created_at"',
            content
        )
        
        if content != original:
            with open(fpath, "w", encoding="utf-8") as f:
                f.write(content)
            print(f"FIXED: {fpath}")
        else:
            print(f"No changes needed: {fpath}")
    except FileNotFoundError:
        print(f"NOT FOUND: {fpath}")

print("\nDone.")
