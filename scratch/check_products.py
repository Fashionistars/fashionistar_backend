import os
import sys
import django

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from apps.product.models import Product

print("Checking products in database...")
products = Product.objects.all()
print(f"Total products in DB: {products.count()}")

# Print fields
fields = [f.name for p in products[:1] for f in p._meta.get_fields() if not f.is_relation]
print(f"Product fields: {fields}")

# Print first 10 products
for p in products[:10]:
    print(f"- ID: {p.id}, Name: {getattr(p, 'name', None) or getattr(p, 'title', None)}, Price: {getattr(p, 'price', None)}, Status: {getattr(p, 'status', None)}")
