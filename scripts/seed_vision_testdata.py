"""
FASHIONISTAR — Vision Test Data Seeder v2 (Schema-Correct)
==========================================================
Run:  uv run python scripts/seed_vision_testdata.py
      (from fashionistar_backend/ directory)

Schema-corrected based on actual model inspection:
  • Product.title  (not .name)
  • Product.stock_qty (not .inventory_count)
  • Product.vendor → VendorProfile FK
  • Category has no .description field
  • VendorProfile: use filter() not get_or_create() to avoid slug constraint
"""

import os
import sys
import decimal
from pathlib import Path

# ── Django setup ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")

import django
django.setup()

# ── Imports (after django.setup) ───────────────────────────────────────────────
from django.contrib.auth import get_user_model
from django.db import transaction

UnifiedUser = get_user_model()

# ─── Credentials ──────────────────────────────────────────────────────────────
ADMIN_EMAIL    = "admin@fashionistar.io"
ADMIN_PASSWORD = "FashionAdmin2026!"

VENDOR_EMAIL    = "vendor.vision.2026@gmail.com"
VENDOR_PASSWORD = "VendorTest@2026!"

CLIENT_EMAIL    = "client.vision.2026@gmail.com"
CLIENT_PASSWORD = "ClientTest@2026!"

# ─── Product definitions (using actual field names: title, stock_qty) ─────────
PRODUCTS = [
    {
        "title": "Royal Agbada Set",
        "description": "Exquisite hand-stitched royal agbada set. Premium Aso-Oke fabric with intricate gold thread embroidery for grand occasions.",
        "price": decimal.Decimal("85000.00"),
        "stock_qty": 15,
        "category_slug": "traditional",
        "status": "published",
    },
    {
        "title": "Ankara Cocktail Dress",
        "description": "Vibrant Ankara cocktail dress with modern silhouette. Perfect for celebrations, dinner parties, and cultural events.",
        "price": decimal.Decimal("45000.00"),
        "stock_qty": 20,
        "category_slug": "women",
        "status": "published",
    },
    {
        "title": "Senator Corporate Suit",
        "description": "Distinguished senator suit for executive boardrooms. Tailored with premium Italian-inspired fabric and hand-finished details.",
        "price": decimal.Decimal("120000.00"),
        "stock_qty": 10,
        "category_slug": "men",
        "status": "published",
    },
    {
        "title": "Asoebi Lace Gown",
        "description": "Elegant aso-ebi lace gown for weddings and traditional ceremonies. Beautifully crafted with premium French lace.",
        "price": decimal.Decimal("65000.00"),
        "stock_qty": 8,
        "category_slug": "women",
        "status": "published",
    },
    {
        "title": "Kids Dashiki Collection",
        "description": "Vibrant kids dashiki set for cultural events and festivities. Comfortable, durable, with authentic African heritage patterns.",
        "price": decimal.Decimal("22000.00"),
        "stock_qty": 30,
        "category_slug": "kids",
        "status": "published",
    },
]

CATEGORIES = [
    {"name": "Traditional", "slug": "traditional"},
    {"name": "Women",       "slug": "women"},
    {"name": "Men",         "slug": "men"},
    {"name": "Kids",        "slug": "kids"},
]


def log(msg: str, icon: str = "→") -> None:
    print(f"  {icon}  {msg}")


# ─── Admin ────────────────────────────────────────────────────────────────────
def seed_admin() -> object:
    log("Seeding admin superuser ...", "🔑")
    user, created = UnifiedUser.objects.get_or_create(
        email=ADMIN_EMAIL,
        defaults={
            "first_name": "Fashion",
            "last_name": "Admin",
            "role": "admin",
            "auth_provider": "email",
        },
    )
    user.set_password(ADMIN_PASSWORD)
    user.is_active = True
    user.is_verified = True
    user.is_staff = True
    user.is_superuser = True
    user.save(update_fields=["password", "is_active", "is_verified", "is_staff", "is_superuser"])
    log(f"Admin {ADMIN_EMAIL} → {'created' if created else 'updated'}", "✅")
    return user


# ─── Vendor ───────────────────────────────────────────────────────────────────
def seed_vendor() -> object:
    log("Seeding vendor user ...", "🏪")
    user, created = UnifiedUser.objects.get_or_create(
        email=VENDOR_EMAIL,
        defaults={
            "first_name": "TestVendor",
            "last_name": "Vision2026",
            "role": "vendor",
            "auth_provider": "email",
        },
    )
    user.set_password(VENDOR_PASSWORD)
    user.is_active = True
    user.is_verified = True
    user.save(update_fields=["password", "is_active", "is_verified"])
    log(f"Vendor {VENDOR_EMAIL} → {'created' if created else 'updated'}", "✅")

    # VendorProfile — use filter to avoid slug constraint
    try:
        from apps.vendor.models import VendorProfile
        profile = VendorProfile.objects.filter(user=user).first()
        if profile is None:
            profile = VendorProfile(user=user)

        if not getattr(profile, "store_name", None):
            profile.store_name = "Adaeze Couture"
        profile.city = "Lagos"
        profile.state = "Lagos"
        profile.country = "Nigeria"
        profile.address = "10 Kingsway Road"

        for field in ["is_active", "is_verified"]:
            if hasattr(profile, field):
                setattr(profile, field, True)

        for field, value in [
            ("account_name", "Adaeze Vision"),
            ("bank_name", "Zenith Bank"),
            ("account_number", "1012345678"),
            ("description", "Custom African luxury styles and designs."),
        ]:
            if hasattr(profile, field):
                setattr(profile, field, value)

        profile.save()
        log("VendorProfile 'Adaeze Couture' saved", "✅")
    except Exception as e:
        log(f"VendorProfile skip: {e}", "⚠️")

    return user


# ─── Client ───────────────────────────────────────────────────────────────────
def seed_client() -> object:
    log("Seeding client user ...", "👤")
    user, created = UnifiedUser.objects.get_or_create(
        email=CLIENT_EMAIL,
        defaults={
            "first_name": "TestClient",
            "last_name": "Vision2026",
            "role": "client",
            "auth_provider": "email",
        },
    )
    user.set_password(CLIENT_PASSWORD)
    user.is_active = True
    user.is_verified = True
    user.save(update_fields=["password", "is_active", "is_verified"])
    log(f"Client {CLIENT_EMAIL} → {'created' if created else 'updated'}", "✅")

    try:
        from apps.client.models import ClientProfile
        if hasattr(ClientProfile, "get_or_create_for_user"):
            profile = ClientProfile.get_or_create_for_user(user)
        else:
            profile, _ = ClientProfile.objects.get_or_create(user=user)

        profile.default_shipping_address = "10 Kingsway Road, Ikoyi, Lagos"
        profile.state = "Lagos"
        profile.country = "Nigeria"
        if hasattr(profile, "is_profile_complete"):
            profile.is_profile_complete = True
        profile.save()
        log("ClientProfile saved", "✅")
    except Exception as e:
        log(f"ClientProfile skip: {e}", "⚠️")

    return user


# ─── Categories ───────────────────────────────────────────────────────────────
def seed_categories() -> dict:
    log("Seeding catalog categories ...", "📂")
    category_map = {}
    try:
        from apps.catalog.models import Category
        # Inspect actual model fields
        actual_fields = {f.name for f in Category._meta.get_fields() if hasattr(f, "name")}
        log(f"Category fields: {sorted(actual_fields)}", "  ℹ")

        for cat_data in CATEGORIES:
            # Try by slug first
            cat = Category.objects.filter(slug=cat_data["slug"]).first()
            if not cat:
                cat = Category.objects.filter(name=cat_data["name"]).first()
            if not cat:
                kwargs: dict = {"name": cat_data["name"]}
                if "slug" in actual_fields:
                    kwargs["slug"] = cat_data["slug"]
                # Explicitly activate — CatalogSelector filters active=True
                if "active" in actual_fields:
                    kwargs["active"] = True
                cat = Category.objects.create(**kwargs)
                log(f"Category '{cat_data['name']}' → created (active=True)", "  ✅")
            else:
                # Ensure existing categories are also active
                if hasattr(cat, "active") and not cat.active:
                    cat.active = True
                    cat.save(update_fields=["active"])
                log(f"Category '{cat_data['name']}' → exists (id={cat.pk}, active={getattr(cat, 'active', '?')})", "  ✅")
            category_map[cat_data["slug"]] = cat
    except Exception as e:
        log(f"Category seeding failed: {e}", "⚠️")
    return category_map


# ─── Products ─────────────────────────────────────────────────────────────────
def seed_products(vendor_user: object, category_map: dict) -> list:
    log("Seeding 5 products ...", "🛍️")
    seeded = []

    try:
        from apps.product.models import Product
    except ImportError as e:
        log(f"Product model import failed: {e}", "⚠️")
        return seeded

    # Get VendorProfile for vendor FK
    vendor_profile = None
    try:
        from apps.vendor.models import VendorProfile
        vendor_profile = VendorProfile.objects.filter(user=vendor_user).first()
        if vendor_profile:
            log(f"Using VendorProfile id={vendor_profile.pk}", "  ℹ")
        else:
            log("No VendorProfile found — products will fail if vendor FK is required", "  ⚠️")
    except Exception as e:
        log(f"VendorProfile lookup failed: {e}", "  ⚠️")

    # Inspect Product model fields
    actual_fields = {f.name for f in Product._meta.get_fields() if hasattr(f, "name")}
    log(f"Product title field: {'title' if 'title' in actual_fields else 'name' if 'name' in actual_fields else 'UNKNOWN'}", "  ℹ")

    title_field = "title" if "title" in actual_fields else "name"
    inv_field   = "stock_qty" if "stock_qty" in actual_fields else "inventory_count" if "inventory_count" in actual_fields else None

    for i, pd in enumerate(PRODUCTS, start=1):
        log(f"[{i}/5] '{pd['title']}' ...", "  →")
        try:
            create_kwargs: dict = {
                title_field: pd["title"],
                "description": pd["description"],
                "price": pd["price"],
                "status": pd["status"],
            }
            if inv_field:
                create_kwargs[inv_field] = pd["stock_qty"]

            if vendor_profile:
                create_kwargs["vendor"] = vendor_profile
            else:
                log(f"    No VendorProfile — skipping remaining products", "  ⚠️")
                break

            # Category FK
            cat = category_map.get(pd["category_slug"])
            if cat and "categories" in actual_fields:
                # M2M — handle after create
                pass
            elif cat and "category" in actual_fields:
                create_kwargs["category"] = cat

            # Upsert by title + vendor
            existing = Product.objects.filter(
                **{title_field: pd["title"], "vendor": vendor_profile}
            ).first()

            if existing:
                for k, v in create_kwargs.items():
                    setattr(existing, k, v)
                existing.save()
                p = existing
                log(f"    '{pd['title']}' ₦{pd['price']} → updated", "  ✅")
            else:
                p = Product.objects.create(**create_kwargs)
                log(f"    '{pd['title']}' ₦{pd['price']} → created", "  ✅")

            # Assign M2M category if applicable
            if cat and "categories" in actual_fields and hasattr(p, "categories"):
                try:
                    p.categories.add(cat)
                    log(f"    Category '{cat.name}' added to product", "  ✅")
                except Exception as e_cat:
                    log(f"    Category M2M skip: {e_cat}", "  ⚠️")

            seeded.append(p)
        except Exception as e:
            log(f"    '{pd['title']}' FAILED: {e}", "  ❌")

    log(f"Products seeded: {len(seeded)}/5", "📊")
    return seeded


# ─── Main ─────────────────────────────────────────────────────────────────────
@transaction.atomic
def run_seed():
    print("=" * 60)
    print("  🚀 FASHIONISTAR — Vision Test Data Seeder v2")
    print(f"  📅 2026-05-28 | Env: {os.environ.get('DJANGO_SETTINGS_MODULE')}")
    print("=" * 60)

    admin_user  = seed_admin()
    vendor_user = seed_vendor()
    client_user = seed_client()
    categories  = seed_categories()
    products    = seed_products(vendor_user, categories)

    print("\n" + "=" * 60)
    print("  📊 SEED SUMMARY")
    print("=" * 60)
    print(f"  ✅ Admin      : {ADMIN_EMAIL}")
    print(f"  ✅ Vendor     : {VENDOR_EMAIL}")
    print(f"  ✅ Client     : {CLIENT_EMAIL}")
    print(f"  ✅ Categories : {len(categories)}")
    print(f"  ✅ Products   : {len(products)}/5")
    print("=" * 60)
    print()
    if len(products) < 5:
        print("  ⚠️  Product seeding incomplete — check errors above.")
        print("  ℹ  You can also seed manually via the vendor dashboard:")
        print(f"     {os.environ.get('NEXT_PUBLIC_FRONTEND_TUNNEL_URL', 'http://localhost:3000')}/vendor-dashboard/product/create")
    print()
    print("  ℹ  Run the Playwright suite next:")
    print("  cd fashionista_frontend")
    print("  $env:PLAYWRIGHT_SKIP_WEB_SERVER=1")
    print("  pnpm exec playwright test tests/e2e/master-vision-e2e-2026-05-28.spec.ts --project=\"chromium — Desktop\" --reporter=list")
    print()


if __name__ == "__main__":
    run_seed()
