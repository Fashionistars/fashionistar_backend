import os
import sys
import django

def main():
    PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    if PROJECT_ROOT not in sys.path:
        sys.path.insert(0, PROJECT_ROOT)

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
    django.setup()

    from apps.product.models import Product

    target_names = [
        "Ankara Cocktail Dress",
        "Royal Agbada Set",
        "Asoebi Lace Gown",
        "Senator Corporate Suit",
        "Kids Dashiki Collection"
    ]

    print("Checking and fixing target products...")
    for name in target_names:
        products = Product.objects.filter(title__icontains=name)
        if not products.exists():
            products = Product.objects.filter(slug__icontains=name.lower().replace(' ', '-'))
            
        if products.exists():
            for p in products:
                print(f"Fixing product: {p.title} (ID: {p.id})")
                p.stock_qty = 100
                p.in_stock = True
                p.is_customisable = True
                p.requires_measurement = True
                p.status = 'published'
                p.save()
                print(f"  -> Saved: stock={p.stock_qty}, in_stock={p.in_stock}, is_customisable={p.is_customisable}")
        else:
            print(f"Product not found: {name}")

if __name__ == '__main__':
    main()
