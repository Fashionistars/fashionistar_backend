"""
qa_create_users.py
==================
Creates the 3 canonical QA test users (client, vendor, admin) and
immediately sets is_active=True + is_verified=True so the frontend
can log in without waiting for OTP delivery.

Usage:
    uv run python scripts/qa_create_users.py
"""

import os
import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from apps.authentication.models import UnifiedUser  # noqa: E402


def create_or_get(email, password, role, first="Test", last="User"):
    try:
        user = UnifiedUser.objects.get(email=email)
        created = False
    except UnifiedUser.DoesNotExist:
        user = UnifiedUser.objects.create_user(
            email=email,
            password=password,
            first_name=first,
            last_name=last,
            user_type=role,
        )
        created = True

    user.is_active = True
    user.is_verified = True
    if hasattr(user, "is_deleted"):
        user.is_deleted = False
    user.set_password(password)
    user.save()
    return user, "CREATED" if created else "UPDATED"


print("=" * 60)
print("  FASHIONISTAR — QA Test User Setup")
print("=" * 60)

# ── Client ─────────────────────────────────────────────────────
c, cs = create_or_get(
    "qa.client@fashionistar.test", "QaClient@2026!", "client", "QA", "Client"
)
print(f"\n  CLIENT [{cs}+VERIFIED]")
print(f"    email      : {c.email}")
print(f"    password   : QaClient@2026!")
print(f"    is_active  : {c.is_active}")
print(f"    is_verified: {c.is_verified}")
print(f"    user_type  : {getattr(c, 'user_type', 'N/A')}")

# ── Vendor ─────────────────────────────────────────────────────
v, vs = create_or_get(
    "qa.vendor@fashionistar.test", "QaVendor@2026!", "vendor", "QA", "Vendor"
)
print(f"\n  VENDOR [{vs}+VERIFIED]")
print(f"    email      : {v.email}")
print(f"    password   : QaVendor@2026!")
print(f"    is_active  : {v.is_active}")
print(f"    is_verified: {v.is_verified}")
print(f"    user_type  : {getattr(v, 'user_type', 'N/A')}")

# ── Admin ──────────────────────────────────────────────────────
try:
    a = UnifiedUser.objects.get(email="qa.admin@fashionistar.test")
    a_created = False
except UnifiedUser.DoesNotExist:
    a = UnifiedUser.objects.create_superuser(
        email="qa.admin@fashionistar.test",
        password="QaAdmin@2026!",
        first_name="QA",
        last_name="Admin",
    )
    a_created = True

a.is_active = True
a.is_verified = True
a.is_staff = True
a.is_superuser = True
if hasattr(a, "is_deleted"):
    a.is_deleted = False
a.set_password("QaAdmin@2026!")
a.save()
astatus = "CREATED" if a_created else "UPDATED"

print(f"\n  ADMIN [{astatus}+VERIFIED]")
print(f"    email       : {a.email}")
print(f"    password    : QaAdmin@2026!")
print(f"    is_active   : {a.is_active}")
print(f"    is_verified : {a.is_verified}")
print(f"    is_superuser: {a.is_superuser}")
print(f"    user_type   : {getattr(a, 'user_type', 'N/A')}")

print("\n" + "=" * 60)
print("  ALL QA USERS READY — No OTP needed, login immediately.")
print("=" * 60)
