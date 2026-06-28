import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from apps.authentication.models import UnifiedUser
from django.apps import apps

u = UnifiedUser.objects.get(email="qa.vendor@fashionistar.test")
VP = apps.get_model("vendor", "VendorProfile")

print("VendorProfile required fields:")
required = []
for f in VP._meta.get_fields():
    if hasattr(f, "null") and not f.null and not getattr(f, "blank", True) and not getattr(f, "has_default", False):
        required.append(f.name)
    if hasattr(f, "name"):
        null_v = getattr(f, "null", "?")
        blank_v = getattr(f, "blank", "?")
        default_v = getattr(f, "default", "?")
        print(f"  {f.name}: null={null_v}, blank={blank_v}, default={default_v}")

print()
print("Attempting to create minimal VendorProfile...")
try:
    vp, created = VP.objects.get_or_create(user=u, defaults={"shop_name": "QA Vendor Shop"})
    print(f"VendorProfile: created={created}, pk={vp.pk}")
    print(f"  shop_name: {getattr(vp, 'shop_name', 'N/A')}")
    print(f"  is_verified: {getattr(vp, 'is_verified', 'N/A')}")
except Exception as e:
    print(f"ERROR: {e}")
    import traceback
    traceback.print_exc()

    print()
    print("Trying with all-nulls approach...")
    try:
        vp = VP(user=u)
        vp.shop_name = "QA Vendor Shop"
        vp.save()
        print(f"Created VendorProfile pk={vp.pk}")
    except Exception as e2:
        print(f"ERROR2: {e2}")
        traceback.print_exc()
