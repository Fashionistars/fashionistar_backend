"""Seed catalog data: Brand + 3 Categories, attach to products."""
import django
import os
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")
django.setup()

from django.contrib.auth import get_user_model
User = get_user_model()

admin = User.objects.get(email="admin@fashionistar.test")
print(f"Admin: {admin.email}")

from apps.catalog.models import Brand, Category

b, c = Brand.objects.get_or_create(
    slug="fashionistar-label",
    defaults={"title": "FashionistarLabel", "description": "House brand for demo products", "active": True, "user": admin},
)
print(f"Brand: {b.title} ({'created' if c else 'exists'})")

cats = [
    ("womens-fashion",   "Women's Fashion"),
    ("mens-fashion",     "Men's Fashion"),
    ("accessories",      "Accessories"),
]
cat_objs = []
for slug, name in cats:
    obj, cr = Category.objects.get_or_create(slug=slug, defaults={"name": name, "active": True, "user": admin})
    cat_objs.append(obj)
    print(f"Category: {obj.name} ({'created' if cr else 'exists'})")

from apps.product.models import Product
for p in Product.objects.all():
    p.categories.set(cat_objs[:1])  # attach Women's Fashion
    print(f"  Attached '{cat_objs[0].name}' to: {p.title}")

print("\n=== Catalog seed complete ===")
print(f"Brands: {Brand.objects.count()} | Categories: {Category.objects.count()} | Products: {Product.objects.count()}")
