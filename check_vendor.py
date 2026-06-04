import os
os.environ["DJANGO_SETTINGS_MODULE"] = "backend.config.development"
import django
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()
u = User.objects.get(email="dezichi1999@gmail.com")
print("User:", u.email, "| role:", u.role, "| active:", u.is_active)

# Check vendor profile via reverse relation
try:
    vp = u.vendor_profile
    print("VendorProfile found:")
    print("  store_name:", getattr(vp, "store_name", "N/A"))
    print("  status:", getattr(vp, "status", "N/A"))
    print("  is_verified:", getattr(vp, "is_verified", "N/A"))
    print("  setup_step:", getattr(vp, "setup_step", "N/A"))
except Exception as e:
    print("No vendor_profile:", e)
