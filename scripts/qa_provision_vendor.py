"""
qa_provision_vendor.py
======================
Provisions a complete VendorProfile + VendorSetupState for the QA vendor user.
Safe to run multiple times (idempotent get_or_create logic).

Usage:
    uv run manage.py shell -c "exec(open('scripts/qa_provision_vendor.py').read())"
"""
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")

# Only call setup() if Django is not already configured
if not django.conf.settings.configured:
    django.setup()

from apps.authentication.models import UnifiedUser
from django.apps import apps

print("=" * 60)
print("  FASHIONISTAR — QA Vendor Profile Provisioning")
print("=" * 60)

# ── 1. Ensure vendor user exists & is active ───────────────────
try:
    vendor_user = UnifiedUser.objects.get(email="qa.vendor@fashionistar.test")
    vendor_user.is_active   = True
    vendor_user.is_verified = True
    if hasattr(vendor_user, "is_deleted"):
        vendor_user.is_deleted = False
    vendor_user.save(update_fields=["is_active", "is_verified"])
    print(f"\n  USER  : {vendor_user.email} [active={vendor_user.is_active}]")
except UnifiedUser.DoesNotExist:
    print("  ERROR : qa.vendor@fashionistar.test does not exist — run qa_create_users.py first")
    raise SystemExit(1)

# ── 2. VendorProfile ────────────────────────────────────────────
VP = apps.get_model("vendor", "VendorProfile")

# Inspect what field names exist on the model
field_names = [f.name for f in VP._meta.get_fields() if hasattr(f, "column")]
print(f"\n  VendorProfile model fields: {field_names}")

store_name_field = "store_name" if "store_name" in field_names else "shop_name"
print(f"  Using store-name field: '{store_name_field}'")

vp_defaults = {store_name_field: "QA Fashion Store"}

# Optional enrichment fields (added only if model has them)
optional_fields = {
    "store_slug":   "qa-fashion-store",
    "tagline":      "Quality Fashion for Everyone",
    "description":  "QA test vendor store for automated E2E testing.",
    "city":         "Lagos",
    "state":        "Lagos",
    "country":      "Nigeria",
    "whatsapp":     "+2348000000000",
    "is_active":    True,
    "is_verified":  True,
    "is_featured":  False,
}
for k, v in optional_fields.items():
    if k in field_names:
        vp_defaults[k] = v

try:
    vp, vp_created = VP.objects.get_or_create(user=vendor_user, defaults=vp_defaults)

    # Ensure activation even if already existed
    if not vp_created:
        if "is_active" in field_names:
            vp.is_active = True
        if "is_verified" in field_names:
            vp.is_verified = True
        vp.save()

    print(f"\n  VENDOR PROFILE [{('CREATED' if vp_created else 'UPDATED')}]")
    print(f"    pk           : {vp.pk}")
    print(f"    store_name   : {getattr(vp, store_name_field, 'N/A')}")
    print(f"    is_active    : {getattr(vp, 'is_active', 'N/A')}")
    print(f"    is_verified  : {getattr(vp, 'is_verified', 'N/A')}")

except Exception as exc:
    print(f"\n  ERROR creating VendorProfile: {exc}")
    import traceback; traceback.print_exc()
    raise SystemExit(1)

# ── 3. VendorSetupState ─────────────────────────────────────────
try:
    VSS = apps.get_model("vendor", "VendorSetupState")
    vss, vss_created = VSS.objects.get_or_create(vendor=vp, defaults={
        "current_step":          4,
        "profile_complete":      True,
        "bank_details":          False,   # Not required for QA testing
        "id_verified":           False,   # KYC gated — not required
        "first_product":         False,
        "onboarding_done":       False,
        "completion_percentage": 50,
    })
    print(f"\n  SETUP STATE [{'CREATED' if vss_created else 'EXISTS'}]")
    print(f"    profile_complete     : {vss.profile_complete}")
    print(f"    completion_percentage: {vss.completion_percentage}%")
except LookupError:
    print("\n  VendorSetupState model not found — skipping (non-critical)")
except Exception as exc:
    print(f"\n  WARNING: VendorSetupState creation failed: {exc}")

print("\n" + "=" * 60)
print("  QA VENDOR FULLY PROVISIONED — login immediately.")
print("  email   : qa.vendor@fashionistar.test")
print("  password: QaVendor@2026!")
print("=" * 60)
