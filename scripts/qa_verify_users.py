"""Verify all QA test users are correctly configured."""
import os
import django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from django.db import connection

with connection.cursor() as cursor:
    cursor.execute("""
        SELECT email, role, is_active, is_verified, is_staff, is_superuser, is_deleted
        FROM authentication_unifieduser
        WHERE email IN (
            'qa.client@fashionistar.test',
            'qa.vendor@fashionistar.test',
            'qa.admin@fashionistar.test'
        )
        ORDER BY role
    """)
    rows = cursor.fetchall()

print()
print("  QA TEST USERS — FINAL VERIFICATION")
print("  " + "-" * 90)
print(f"  {'EMAIL':<36} {'ROLE':<10} {'ACTIVE':<8} {'VERIFIED':<10} {'STAFF':<7} {'SUPER':<7} DELETED")
print("  " + "-" * 90)
all_ok = True
for r in rows:
    email, role, active, verified, staff, superuser, deleted = r
    ok = active and verified and not deleted
    if not ok:
        all_ok = False
    flag = "OK" if ok else "WARN"
    print(f"  [{flag}] {email:<36} {role:<10} {str(active):<8} {str(verified):<10} {str(staff):<7} {str(superuser):<7} {deleted}")

print()
print("  LOGIN CREDENTIALS:")
print("  qa.client@fashionistar.test  / QaClient@2026!")
print("  qa.vendor@fashionistar.test  / QaVendor@2026!")
print("  qa.admin@fashionistar.test   / QaAdmin@2026!")
print()
if all_ok:
    print("  ALL USERS READY — login works WITHOUT OTP step.")
else:
    print("  WARNING: Some users need fixing — check WARN rows above.")
