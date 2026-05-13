import os, django, traceback
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from apps.authentication.models import UnifiedUser
from apps.vendor.selectors.vendor_selectors import get_vendor_profile_or_none
from django.apps import apps

u = UnifiedUser.objects.get(email="qa.vendor@fashionistar.test")
print(f"User: {u.email} | role: {u.role} | active: {u.is_active}")

try:
    profile = get_vendor_profile_or_none(u)
    print(f"Profile from selector: {profile}")
except Exception as e:
    print(f"ERROR in selector: {e}")
    traceback.print_exc()
    profile = None

if profile:
    print(f"  store_name: {profile.store_name}")
    VP = apps.get_model("vendor", "VendorProfile")
    print(f"  Products count: {profile.vendor_products.count()}")
    
    # Test get_queryset logic manually
    try:
        qs = profile.vendor_products.all()
        products = list(qs.values("id", "title", "price", "stock_qty", "status", "categories__name", "date").order_by("-date"))
        print(f"  Products list: {products}")
    except Exception as e:
        print(f"  Products values() error: {e}")
        traceback.print_exc()

    # Test analytics methods
    try:
        print(f"  get_todays_sales: {profile.get_todays_sales()}")
    except Exception as e:
        print(f"  get_todays_sales error: {e}")
        traceback.print_exc()
else:
    print("SELECTOR RETURNED None — this is the root cause")
    print("Checking if selector has a bug:")
    VP = apps.get_model("vendor", "VendorProfile")
    direct = VP.objects.filter(user=u).first()
    print(f"  Direct VP.objects.filter(user): {direct}")
