"""
Django Management Command: seed_e2e_data
=========================================
Usage:
    uv run python manage.py seed_e2e_data

Creates all test users (admin, vendor, client), auto-verifies them,
seeds catalog (brand, category), vendor profile, and 3 products.
Safe to run multiple times (idempotent).
"""

from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

User = get_user_model()

DIVIDER = "=" * 68


class Command(BaseCommand):
    """Seed live E2E test data: users, catalog, vendor, products."""

    help = "Seed live E2E test data (admin, vendor, client, catalog, products)"

    # ── helpers ──────────────────────────────────────────────────────────────

    def _upsert_user(
        self,
        email: str,
        password: str,
        first_name: str,
        last_name: str,
        role: str,
        is_superuser: bool = False,
        is_staff: bool = False,
    ) -> tuple:
        """
        Create or update a unified user and ensure they are verified and active.

        The UnifiedUser model requires EITHER email OR phone (not both) during
        creation, and requires a non-blank password. We create via email-only,
        calling set_password() before save().

        Args:
            email: User email address (used as lookup key).
            password: Plain-text password (will be hashed).
            first_name: First name.
            last_name: Last name.
            role: Role slug (must be a valid ROLE_CHOICES value).
            is_superuser: Whether to grant superuser privileges.
            is_staff: Whether to grant staff (Django admin) access.

        Returns:
            Tuple of (user instance, created bool).
        """
        try:
            user = User.objects.get(email=email)
            created = False
        except User.DoesNotExist:
            user = User(
                email=email,
                first_name=first_name,
                last_name=last_name,
                is_superuser=is_superuser,
                is_staff=is_staff,
                is_active=True,
            )
            try:
                User._meta.get_field("role")
                user.role = role
            except Exception:
                pass
            try:
                User._meta.get_field("is_verified")
                user.is_verified = True
            except Exception:
                pass
            user.set_password(password)
            user.save()
            created = True

        if not created:
            # Ensure verified / active on existing users
            update_fields = ["password"]
            if not user.is_active:
                user.is_active = True
                update_fields.append("is_active")
            if hasattr(user, "is_verified") and not user.is_verified:
                user.is_verified = True
                update_fields.append("is_verified")
            user.set_password(password)
            user.save(update_fields=update_fields)

        return user, created

    # ── main ─────────────────────────────────────────────────────────────────

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003
        """Execute seed command."""
        self.stdout.write(f"\n{DIVIDER}")
        self.stdout.write("  FASHIONISTAR — Live E2E Seed Command")
        self.stdout.write(DIVIDER)

        # ── Detect valid roles ─────────────────────────────────────────────
        ROLE_ADMIN  = "admin"
        ROLE_VENDOR = "vendor"
        ROLE_CLIENT = "client"

        try:
            choices = [c[0] for c in User._meta.get_field("role").choices]
            if "superadmin" in choices:
                ROLE_ADMIN = "superadmin"
            elif "super_admin" in choices and "admin" not in choices:
                ROLE_ADMIN = "super_admin"
            if "customer" in choices and "client" not in choices:
                ROLE_CLIENT = "customer"
            self.stdout.write(f"  Detected roles: {choices}")
        except Exception:
            pass

        # ── Step 1: Users ──────────────────────────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING("\n[STEP 1] Creating / verifying test users..."))

        admin_user, c = self._upsert_user(
            email="admin@fashionistar.test",
            password="Admin@Secure99!",
            first_name="Admin",
            last_name="Fashionistar",
            role=ROLE_ADMIN,
            is_superuser=True,
            is_staff=True,
        )
        self.stdout.write(self.style.SUCCESS(
            f"  [{'CREATED' if c else 'UPDATED'}] ADMIN: {admin_user.email}"
        ))

        vendor_user, c = self._upsert_user(
            email="vendor@fashionistar.test",
            password="Vendor@Secure99!",
            first_name="Amaka",
            last_name="Osei",
            role=ROLE_VENDOR,
        )
        self.stdout.write(self.style.SUCCESS(
            f"  [{'CREATED' if c else 'UPDATED'}] VENDOR: {vendor_user.email}"
        ))

        client_user, c = self._upsert_user(
            email="client@fashionistar.test",
            password="Client@Secure99!",
            first_name="Chidi",
            last_name="Nwosu",
            role=ROLE_CLIENT,
        )
        self.stdout.write(self.style.SUCCESS(
            f"  [{'CREATED' if c else 'UPDATED'}] CLIENT: {client_user.email}"
        ))

        # ── Step 2: Catalog fixtures ───────────────────────────────────────
        # Brand fields: title, slug, description, image, active, user
        # Category fields: name, slug, image, active, user
        # Collection does NOT exist in apps.catalog — skip
        self.stdout.write(self.style.MIGRATE_HEADING("\n[STEP 2] Creating catalog fixtures..."))
        brand = category = None
        try:
            from apps.catalog.models import Brand, Category  # noqa: PLC0415

            brand, _ = Brand.objects.get_or_create(
                slug="fashionistar-label",
                defaults={
                    "title": "FashionistarLabel",
                    "description": "House brand for demo products",
                    "active": True,
                    "user": admin_user,
                },
            )
            self.stdout.write(self.style.SUCCESS(f"  ✓ Brand: {brand.title}"))

            category, _ = Category.objects.get_or_create(
                slug="womens-fashion",
                defaults={
                    "name": "Women's Fashion",
                    "active": True,
                    "user": admin_user,
                },
            )
            self.stdout.write(self.style.SUCCESS(f"  ✓ Category: {category.name}"))

        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  ⚠ Catalog error: {exc}"))

        # ── Step 3: Vendor profile ─────────────────────────────────────────
        # VendorProfile fields: user, store_name, store_slug, tagline, description,
        # logo_url, cover_url, city, state, country, address, is_verified, is_active,
        # is_featured
        self.stdout.write(self.style.MIGRATE_HEADING("\n[STEP 3] Setting up vendor profile & store..."))
        vendor_profile = None
        try:
            from apps.vendor.models import VendorProfile  # noqa: PLC0415

            vendor_profile, created = VendorProfile.objects.get_or_create(
                user=vendor_user,
                defaults={
                    "store_name": "Amaka's Atelier",
                    "store_slug": "amakas-atelier",
                    "tagline": "Premium African Fashion",
                    "description": "Curated African fashion by Amaka Osei",
                    "city": "Lagos",
                    "state": "Lagos",
                    "country": "NG",
                    "address": "15 Lagos Island, Lagos, Nigeria",
                    "is_verified": True,
                    "is_active": True,
                    "is_featured": False,
                },
            )
            if not created:
                vendor_profile.is_verified = True
                vendor_profile.is_active = True
                vendor_profile.save(update_fields=["is_verified", "is_active"])

            status = "CREATED" if created else "UPDATED"
            self.stdout.write(self.style.SUCCESS(
                f"  [{status}] VendorProfile: {vendor_profile.store_name}"
            ))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  ⚠ VendorProfile failed: {exc}"))

        # ── Step 4: KYC auto-approve ───────────────────────────────────────
        # KYC model is KycDocument or KycSubmission
        self.stdout.write(self.style.MIGRATE_HEADING("\n[STEP 4] Auto-approving vendor KYC..."))
        try:
            from apps.kyc.models import KycDocument  # noqa: PLC0415
            kyc_fields = [f.name for f in KycDocument._meta.get_fields() if hasattr(f, "column")]
            self.stdout.write(f"  KycDocument fields: {kyc_fields}")
            kyc_defaults = {"user": vendor_user}
            if "status" in kyc_fields:
                kyc_defaults["status"] = "approved"
            if "is_verified" in kyc_fields:
                kyc_defaults["is_verified"] = True
            kyc, created = KycDocument.objects.get_or_create(
                user=vendor_user,
                defaults=kyc_defaults,
            )
            if not created:
                if hasattr(kyc, "status"):
                    kyc.status = "approved"
                if hasattr(kyc, "is_verified"):
                    kyc.is_verified = True
                kyc.save()
            status = "CREATED" if created else "UPDATED"
            self.stdout.write(self.style.SUCCESS(f"  [{status}] KycDocument for vendor"))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  ⚠ KYC skip: {exc}"))

        # ── Step 5: Products ───────────────────────────────────────────────
        # Product fields: title, slug, sku, description, short_description,
        # vendor, price, old_price, stock_qty, in_stock, status
        self.stdout.write(self.style.MIGRATE_HEADING("\n[STEP 5] Creating demo products..."))
        product_list = [
            {
                "title": "Ankara Wrap Dress",
                "slug": "ankara-wrap-dress",
                "description": "Bold, vibrant Ankara print wrap dress with adjustable tie waist.",
                "short_description": "Vibrant Ankara wrap dress",
                "price": Decimal("29500.00"),
                "old_price": Decimal("35000.00"),
                "sku": "FAD-001-ANK",
                "stock_qty": 50,
                "in_stock": True,
                "status": "published",
            },
            {
                "title": "Lace Bodycon Gown",
                "slug": "lace-bodycon-gown",
                "description": "Elegant stretch lace bodycon gown for special occasions.",
                "short_description": "Stretch lace bodycon gown",
                "price": Decimal("45000.00"),
                "old_price": Decimal("55000.00"),
                "sku": "FAD-002-LBC",
                "stock_qty": 30,
                "in_stock": True,
                "status": "published",
            },
            {
                "title": "Kaftan Co-Ord Set",
                "slug": "kaftan-coord-set",
                "description": "Modern kaftan co-ord set in premium adire fabric.",
                "short_description": "Premium adire kaftan co-ord",
                "price": Decimal("18500.00"),
                "old_price": Decimal("22000.00"),
                "sku": "FAD-003-KCS",
                "stock_qty": 75,
                "in_stock": True,
                "status": "published",
            },
        ]

        created_products = []
        try:
            from apps.product.models import Product  # noqa: PLC0415

            for pdata in product_list:
                kwargs = dict(pdata)
                kwargs["vendor"] = vendor_profile if vendor_profile else vendor_user

                prod, created = Product.objects.get_or_create(
                    slug=pdata["slug"],
                    defaults=kwargs,
                )
                if not created:
                    Product.objects.filter(pk=prod.pk).update(
                        in_stock=True,
                        stock_qty=pdata["stock_qty"],
                        status="published",
                    )
                    prod.refresh_from_db()

                # Link to category via M2M
                if category:
                    try:
                        prod.categories.add(category)
                    except Exception:
                        pass

                created_products.append(prod)
                self.stdout.write(self.style.SUCCESS(
                    f"  [{'CREATED' if created else 'UPDATED'}] {prod.title} — ₦{prod.price:,.0f}"
                ))

        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  ⚠ Product error: {exc}"))

        # ── Step 6: Wallet (requires currency) ────────────────────────────
        self.stdout.write(self.style.MIGRATE_HEADING("\n[STEP 6] Ensuring wallets exist..."))
        try:
            from apps.wallet.models import Currency, Wallet  # noqa: PLC0415

            # Ensure NGN currency exists first
            ngn, _ = Currency.objects.get_or_create(
                code="NGN",
                defaults={
                    "name": "Nigerian Naira",
                    "symbol": "₦",
                    "decimal_places": 2,
                    "is_active": True,
                    "exchange_rate_usd": Decimal("0.00065"),
                },
            )
            self.stdout.write(self.style.SUCCESS(f"  ✓ Currency: {ngn.code} ({ngn.symbol})"))

            for u in [admin_user, vendor_user, client_user]:
                wallet, created = Wallet.objects.get_or_create(
                    user=u,
                    defaults={
                        "currency": ngn,
                        "name": "Fashionistar Wallet",
                        "is_default": True,
                        "status": "active",
                    },
                )
                self.stdout.write(self.style.SUCCESS(
                    f"  [{'CREATED' if created else 'EXISTS'}] Wallet for {u.email}"
                ))
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"  ⚠ Wallet skip: {exc}"))

        # ── Summary ────────────────────────────────────────────────────────
        self.stdout.write(f"\n{DIVIDER}")
        self.stdout.write(self.style.SUCCESS("  ✅ SEED COMPLETE — Test Credentials"))
        self.stdout.write(DIVIDER)
        self.stdout.write("""
  🔐 ADMIN (superuser)
     Email:    admin@fashionistar.test
     Password: Admin@Secure99!
     URL:      http://localhost:8001/admin/

  🏪 VENDOR
     Email:    vendor@fashionistar.test
     Password: Vendor@Secure99!
     Store:    Amaka's Atelier

  🛒 CLIENT
     Email:    client@fashionistar.test
     Password: Client@Secure99!

  📦 PRODUCTS (3):
     1. Ankara Wrap Dress  — ₦29,500  (slug: ankara-wrap-dress)
     2. Lace Bodycon Gown  — ₦45,000  (slug: lace-bodycon-gown)
     3. Kaftan Co-Ord Set  — ₦18,500  (slug: kaftan-coord-set)

  🌐 FRONTEND:  http://localhost:3000
  ⚙  BACKEND:   http://localhost:8001
  📊 ADMIN:     http://localhost:8001/admin/
  📚 API DOCS:  http://localhost:8001/api/v1/docs/
""")
        self.stdout.write(DIVIDER + "\n")
