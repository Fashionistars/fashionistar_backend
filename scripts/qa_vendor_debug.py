import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from apps.authentication.models import UnifiedUser
from django.test import RequestFactory
from django.contrib.auth.models import AnonymousUser
import traceback

u = UnifiedUser.objects.get(email="qa.vendor@fashionistar.test")
print(f"Vendor user: {u.email} | role: {u.role} | active: {u.is_active}")

from django.apps import apps
VP = apps.get_model("vendor", "VendorProfile")
vp = VP.objects.filter(user=u).first()
print(f"VendorProfile: {vp} | pk: {getattr(vp,'pk','NONE')}")

if vp:
    print(f"  store_name: '{getattr(vp,'store_name','?')}'")
    print(f"  is_active: {getattr(vp,'is_active','?')}")
    print(f"  is_deleted: {getattr(vp,'is_deleted','?')}")
    
    # Try to get vendor products via ORM directly
    try:
        PP = apps.get_model("product", "Product")
        products = PP.objects.filter(vendor=vp)
        print(f"  Products count: {products.count()}")
    except Exception as e:
        print(f"  Product lookup error: {e}")
        traceback.print_exc()
    
    # Try VendorProduct if that's the model name
    for model_name in ["VendorProduct", "ProductListing", "VendorListing"]:
        try:
            M = apps.get_model("vendor", model_name)
            items = M.objects.filter(vendor=vp)
            print(f"  {model_name}.count: {items.count()}")
        except LookupError:
            pass
        except Exception as e:
            print(f"  {model_name} error: {e}")
else:
    print("NO VendorProfile found — this is the root cause of 500")
    print("Creating fresh VendorProfile...")
    vp = VP(user=u, store_name="QA Vendor Shop")
    try:
        vp.save()
        print(f"Created: pk={vp.pk}")
    except Exception as e:
        print(f"Save error: {e}")
        traceback.print_exc()
