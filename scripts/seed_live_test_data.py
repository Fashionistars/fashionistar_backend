"""
Fashionistar — Live E2E Seed Script
=====================================
Run with:
    uv run python manage.py shell < scripts/seed_live_test_data.py

Creates:
  1. SuperAdmin user  (admin@fashionistar.test / Admin@Secure99!)
  2. Vendor  user     (vendor@fashionistar.test / Vendor@Secure99!)
  3. Client  user     (client@fashionistar.test / Client@Secure99!)
  4. Catalog → Category, Brand, Collection
  5. Vendor Profile + Store (business setup complete)
  6. 3 demo Products linked to vendor

All users are auto-verified (is_verified=True, is_active=True).
"""

import django
import os

# ── Setup ────────────────────────────────────────────────────────────────────
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.contrib.auth import get_user_model
from django.utils import timezone
from decimal import Decimal

User = get_user_model()

print("\n" + "=" * 70)
print("  FASHIONISTAR — Live E2E Seed Script")
print("=" * 70)

# ── 1. Helper ─────────────────────────────────────────────────────────────────

def upsert_user(email, phone, password, first_name, last_name, role, is_superuser=False, is_staff=False):
    user, created = User.objects.get_or_create(email=email, defaults={
        "phone_number": phone,
        "first_name": first_name,
        "last_name": last_name,
        "role": role,
        "is_superuser": is_superuser,
        "is_staff": is_staff,
        "is_active": True,
        "is_verified": True,
    })
    if not created:
        # Ensure verification
        changed = False
        if not user.is_active:
            user.is_active = True
            changed = True
        if hasattr(user, "is_verified") and not user.is_verified:
            user.is_verified = True
            changed = True
        if changed:
            user.save(update_fields=["is_active"] + (["is_verified"] if hasattr(user, "is_verified") else []))
    user.set_password(password)
    user.save()
    status = "CREATED" if created else "UPDATED"
    print(f"  [{status}] {role.upper()}: {email} (is_active={user.is_active}, is_verified={getattr(user, 'is_verified', 'N/A')})")
    return user

# ── 2. Users ─────────────────────────────────────────────────────────────────

print("\n[STEP 1] Creating / verifying test users...")

ROLE_ADMIN  = "superadmin"
ROLE_VENDOR = "vendor"
ROLE_CLIENT = "client"

# Try to introspect actual role choices from model
try:
    _choices = [c[0] for c in User._meta.get_field("role").choices]
    if "admin" in _choices and "superadmin" not in _choices:
        ROLE_ADMIN = "admin"
    if "customer" in _choices and "client" not in _choices:
        ROLE_CLIENT = "customer"
    print(f"  Detected role choices: {_choices}")
except Exception:
    pass

admin_user  = upsert_user(
    email="admin@fashionistar.test",
    phone="+2348011110001",
    password="Admin@Secure99!",
    first_name="Admin",
    last_name="Fashionistar",
    role=ROLE_ADMIN,
    is_superuser=True,
    is_staff=True,
)

vendor_user = upsert_user(
    email="vendor@fashionistar.test",
    phone="+2348011110002",
    password="Vendor@Secure99!",
    first_name="Amaka",
    last_name="Osei",
    role=ROLE_VENDOR,
)

client_user = upsert_user(
    email="client@fashionistar.test",
    phone="+2348011110003",
    password="Client@Secure99!",
    first_name="Chidi",
    last_name="Nwosu",
    role=ROLE_CLIENT,
)

# ── 3. Phone Verify records ───────────────────────────────────────────────────

print("\n[STEP 2] Ensuring phone verification records...")
try:
    from apps.phone_verify.models import SMSVerification
    for user in [admin_user, vendor_user, client_user]:
        SMSVerification.objects.filter(phone_number=user.phone_number).update(
            is_verified=True
        )
    print("  ✓ SMSVerification records updated")
except Exception as e:
    print(f"  ⚠ phone_verify skip: {e}")

# ── 4. Catalog — Brand ────────────────────────────────────────────────────────

print("\n[STEP 3] Creating catalog fixtures...")

try:
    from apps.catalog.models import Brand, Category, Collection

    brand, _ = Brand.objects.get_or_create(
        name="FashionistarLabel",
        defaults={
            "slug": "fashionistar-label",
            "description": "House brand for Fashionistar demo products",
            "is_active": True,
        }
    )
    print(f"  ✓ Brand: {brand.name} (id={brand.id})")

    category, _ = Category.objects.get_or_create(
        name="Women's Fashion",
        defaults={
            "slug": "womens-fashion",
            "description": "All women's clothing, accessories, and footwear",
            "is_active": True,
        }
    )
    print(f"  ✓ Category: {category.name} (id={category.id})")

    collection, _ = Collection.objects.get_or_create(
        name="Spring/Summer 2026",
        defaults={
            "slug": "spring-summer-2026",
            "description": "Vibrant SS2026 collection",
            "is_active": True,
        }
    )
    print(f"  ✓ Collection: {collection.name} (id={collection.id})")

except Exception as e:
    print(f"  ⚠ Catalog creation error: {e}")
    brand = category = collection = None

# ── 5. Vendor Profile + Store ─────────────────────────────────────────────────

print("\n[STEP 4] Setting up vendor profile & store...")

vendor_profile = None
try:
    from apps.vendor.models import VendorProfile

    vendor_profile, created = VendorProfile.objects.get_or_create(
        user=vendor_user,
        defaults={
            "business_name": "Amaka's Atelier",
            "business_email": "amaka@fashionistar.test",
            "business_phone": "+2348011110002",
            "business_address": "15 Lagos Island, Lagos, Nigeria",
            "is_approved": True,
            "is_active": True,
            "setup_complete": True,
        }
    )
    if not created:
        vendor_profile.is_approved = True
        vendor_profile.is_active = True
        vendor_profile.setup_complete = True
        vendor_profile.save(update_fields=["is_approved", "is_active", "setup_complete"])

    status = "CREATED" if created else "UPDATED"
    print(f"  [{status}] VendorProfile: {vendor_profile.business_name} (id={vendor_profile.id})")

except Exception as e:
    print(f"  ⚠ VendorProfile creation error: {e}")
    # Try alternative model name
    try:
        from apps.vendor.models import Vendor
        vendor_profile, created = Vendor.objects.get_or_create(
            user=vendor_user,
            defaults={
                "business_name": "Amaka's Atelier",
                "is_approved": True,
                "is_active": True,
            }
        )
        status = "CREATED" if created else "FOUND"
        print(f"  [{status}] Vendor: {vendor_profile.business_name}")
    except Exception as e2:
        print(f"  ⚠ Vendor model error: {e2}")

# ── 6. Vendor KYC (auto-approve) ──────────────────────────────────────────────

print("\n[STEP 5] Auto-approving vendor KYC...")
try:
    from apps.kyc.models import KYCDocument
    kyc, created = KYCDocument.objects.get_or_create(
        user=vendor_user,
        defaults={
            "document_type": "nin",
            "document_number": "12345678901",
            "status": "approved",
            "is_verified": True,
        }
    )
    if not created and kyc.status != "approved":
        kyc.status = "approved"
        kyc.is_verified = True
        kyc.save(update_fields=["status", "is_verified"])
    status = "CREATED" if created else "FOUND/UPDATED"
    print(f"  [{status}] KYC: status={kyc.status}")
except Exception as e:
    print(f"  ⚠ KYC skip: {e}")

# ── 7. Products ───────────────────────────────────────────────────────────────

print("\n[STEP 6] Creating demo products...")

PRODUCTS = [
    {
        "name": "Ankara Wrap Dress",
        "slug": "ankara-wrap-dress",
        "description": "Bold, vibrant Ankara print wrap dress with adjustable tie waist.",
        "price": Decimal("29500.00"),
        "compare_at_price": Decimal("35000.00"),
        "sku": "FAD-001-ANK",
        "stock": 50,
        "is_active": True,
        "is_published": True,
    },
    {
        "name": "Lace Bodycon Gown",
        "slug": "lace-bodycon-gown",
        "description": "Elegant stretch lace bodycon gown, perfect for special occasions.",
        "price": Decimal("45000.00"),
        "compare_at_price": Decimal("55000.00"),
        "sku": "FAD-002-LBC",
        "stock": 30,
        "is_active": True,
        "is_published": True,
    },
    {
        "name": "Kaftan Co-Ord Set",
        "slug": "kaftan-coord-set",
        "description": "Modern kaftan co-ord set in premium adire fabric.",
        "price": Decimal("18500.00"),
        "compare_at_price": Decimal("22000.00"),
        "sku": "FAD-003-KCS",
        "stock": 75,
        "is_active": True,
        "is_published": True,
    },
]

try:
    from apps.product.models import Product

    created_products = []
    for pdata in PRODUCTS:
        kwargs = dict(pdata)
        kwargs["vendor"] = vendor_profile if vendor_profile else vendor_user
        if category:
            kwargs["category"] = category
        if brand:
            kwargs["brand"] = brand

        p, created = Product.objects.get_or_create(
            slug=pdata["slug"],
            defaults=kwargs
        )
        if not created:
            Product.objects.filter(pk=p.pk).update(
                is_active=True, is_published=True, stock=pdata["stock"]
            )
        created_products.append(p)
        status = "CREATED" if created else "UPDATED"
        print(f"  [{status}] Product: {p.name} — ₦{p.price:,.0f} (slug={p.slug})")

    if collection and created_products:
        try:
            collection.products.add(*created_products)
            print(f"  ✓ Products linked to collection: {collection.name}")
        except Exception:
            pass

except Exception as e:
    print(f"  ⚠ Product creation error: {e}")

# ── 8. Wallet ─────────────────────────────────────────────────────────────────

print("\n[STEP 7] Ensuring wallets exist...")
try:
    from apps.wallet.models import Wallet
    for user in [admin_user, vendor_user, client_user]:
        wallet, created = Wallet.objects.get_or_create(user=user)
        status = "CREATED" if created else "EXISTS"
        print(f"  [{status}] Wallet for {user.email}")
except Exception as e:
    print(f"  ⚠ Wallet skip: {e}")

# ── 9. Summary ────────────────────────────────────────────────────────────────

print("\n" + "=" * 70)
print("  ✅ SEED COMPLETE — Test Credentials")
print("=" * 70)
print(f"""
  🔐 SUPERADMIN
     Email:    admin@fashionistar.test
     Password: Admin@Secure99!
     URL:      http://localhost:8000/admin/

  🏪 VENDOR
     Email:    vendor@fashionistar.test
     Password: Vendor@Secure99!
     Store:    Amaka's Atelier

  🛒 CLIENT
     Email:    client@fashionistar.test
     Password: Client@Secure99!

  📦 PRODUCTS (3 created):
     1. Ankara Wrap Dress      — ₦29,500
     2. Lace Bodycon Gown      — ₦45,000
     3. Kaftan Co-Ord Set      — ₦18,500

  🌐 FRONTEND:  http://localhost:3000
  ⚙  BACKEND:   http://localhost:8000
  📊 ADMIN:     http://localhost:8000/admin/
  📚 API DOCS:  http://localhost:8000/api/v1/docs/
""")
print("=" * 70 + "\n")
