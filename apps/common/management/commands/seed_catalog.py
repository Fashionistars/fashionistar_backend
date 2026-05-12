"""Catalog seed management command."""
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    """Seed Brand + Categories and attach to products."""

    help = "Seed catalog: Brand, Category, attach products"

    def handle(self, *args, **options):
        from django.contrib.auth import get_user_model
        from apps.catalog.models import Brand, Category
        from apps.product.models import Product

        User = get_user_model()
        admin = User.objects.get(email="admin@fashionistar.test")
        self.stdout.write(f"Admin: {admin.email}")

        b, c = Brand.objects.get_or_create(
            slug="fashionistar-label",
            defaults={"title": "FashionistarLabel", "description": "House brand", "image": "", "active": True, "user": admin},
        )
        self.stdout.write(self.style.SUCCESS(f"Brand: {b.title} ({'CREATED' if c else 'EXISTS'})"))

        cats_data = [
            ("womens-fashion", "Women's Fashion"),
            ("mens-fashion",   "Men's Fashion"),
            ("accessories",    "Accessories"),
        ]
        womens_cat = None
        for slug, name in cats_data:
            obj, cr = Category.objects.get_or_create(
                slug=slug,
                defaults={"name": name, "image": "", "active": True, "user": admin},
            )
            if womens_cat is None:
                womens_cat = obj
            self.stdout.write(self.style.SUCCESS(f"Category: {obj.name} ({'CREATED' if cr else 'EXISTS'})"))

        for p in Product.objects.all():
            p.categories.add(womens_cat)
            self.stdout.write(f"  → {p.title} tagged [{womens_cat.name}]")

        self.stdout.write(self.style.SUCCESS(
            f"\n=== DONE: {Brand.objects.count()} brand(s) | {Category.objects.count()} cat(s) | {Product.objects.count()} product(s)"
        ))
