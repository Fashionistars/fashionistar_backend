import os
import sys
import django

# Add the project root to sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from django.contrib.auth import get_user_model

User = get_user_model()

print("Checking registered users...")
clients = User.objects.filter(role=User.ROLE_CLIENT)[:5]
print(f"Found {len(clients)} clients:")
for c in clients:
    print(f"- ID: {c.id}, Email: {c.email}, Phone: {c.phone}, Active: {c.is_active}, Verified: {c.is_verified}")

vendors = User.objects.filter(role=User.ROLE_VENDOR)[:5]
print(f"\nFound {len(vendors)} vendors:")
for v in vendors:
    print(f"- ID: {v.id}, Email: {v.email}, Phone: {v.phone}, Active: {v.is_active}, Verified: {v.is_verified}")
