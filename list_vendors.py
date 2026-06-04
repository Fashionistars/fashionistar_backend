import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")

import django
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

print("=== VENDOR ACCOUNTS ===")
vendors = User.objects.filter(user_type="vendor").values(
    "email", "is_active", "date_joined"
).order_by("-date_joined")[:10]
for v in vendors:
    print(f"  {v['email']} | active={v['is_active']} | joined={v['date_joined']}")

if not vendors:
    # fallback — show all users
    print("  (no vendor users found — listing all users)")
    for u in User.objects.values("email", "user_type", "is_active").order_by("-date_joined")[:15]:
        print(f"  {u['email']} | type={u['user_type']} | active={u['is_active']}")
