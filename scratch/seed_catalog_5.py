# scratch/seed_catalog_5.py
import os
import sys
import django
from django.utils import timezone
from django.utils.text import slugify

# Setup Django
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

from django.contrib.auth import get_user_model
from apps.catalog.models import Category, Brand, Collections, BlogPost, BlogMedia, BlogPostStatus

User = get_user_model()

def seed():
    # 1. Ensure admin user exists with correct credentials
    admin_email = "admin@fashionistar.io"
    admin_password = "FashionAdmin2026!"
    
    admin, created = User.objects.get_or_create(
        email=admin_email,
        defaults={
            "first_name": "Fashionistar",
            "last_name": "Admin",
            "role": "admin",
            "is_staff": True,
            "is_superuser": True,
            "is_active": True,
        }
    )
    admin.set_password(admin_password)
    admin.is_staff = True
    admin.is_superuser = True
    admin.save()
    print(f"Admin User: {admin.email} (Created: {created}, Password set to: {admin_password})")

    # 2. Seed 5 Categories
    categories_data = [
        ("Lace & Aso Ebi", "Lace fabrics, detailed embroidery, and traditional Aso Ebi outfits for ceremonies."),
        ("Senators & Kaftans", "Premium linen and cashmere senator suits, long/short sleeve kaftans, and daily tunics."),
        ("Agbada & Ceremonial", "Grand Agbadas, custom hand-embroidered robes, and native ceremonial garments."),
        ("Ready-to-Wear Styles", "Pre-designed African prints, contemporary jumpsuits, dresses, and trousers ready for immediate dispatch."),
        ("Bridal & Custom Gowns", "Bespoke wedding gowns, reception outfits, bridesmaid dresses, and premium custom wear.")
    ]
    
    seeded_categories = []
    for name, desc in categories_data:
        slug = slugify(name)
        cat, cat_created = Category.objects.update_or_create(
            slug=slug,
            defaults={
                "name": name,
                "active": True,
                "user": admin
            }
        )
        seeded_categories.append(cat)
        print(f"Category: {cat.name} (Created: {cat_created})")

    # 3. Seed 5 Brands
    brands_data = [
        ("House of Deola", "Iconic haute couture fashion house specializing in modern African silhouettes."),
        ("Adebayo Jones Couture", "Elegance, luxury, and premium ceremonial couture tailored to perfection."),
        ("Mai Atafo Inspired", "Savile Row-style bespoke tailoring, premium suits, and exquisite bridal collections."),
        ("Tiffany Amber", "Pioneering luxury ready-to-wear brand with flowy, elegant contemporary prints."),
        ("Orange Culture", "Avant-garde design house blending traditional prints with streetwear aesthetics.")
    ]
    
    seeded_brands = []
    for title, desc in brands_data:
        slug = slugify(title)
        brand, b_created = Brand.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "description": desc,
                "active": True,
                "user": admin
            }
        )
        seeded_brands.append(brand)
        print(f"Brand: {brand.title} (Created: {b_created})")

    # 4. Seed 5 Collections
    collections_data = [
        ("Summer Runway Edit", "Breathable materials, chic designs, and high-fashion summer silhouettes.", "Exclusive holiday resort wear."),
        ("Monarch Wedding Collection", "Opulent styles, grand embroidery, and masterfully tailored wedding masterpieces.", "Fit for royalty."),
        ("Urban Streetwise Tailoring", "African print accents combined with modern streetwear tailoring.", "Edgy and bold."),
        ("Heritage Aso Oke Suite", "Timeless hand-woven Aso Oke fabrics turned into stunning contemporary outfits.", "A celebration of legacy."),
        ("Minimalist Kaftan Series", "Monochromatic, cleanly cut, and extremely comfortable senator kaftans.", "Simple is sophisticated.")
    ]
    
    seeded_collections = []
    for title, sub, desc in collections_data:
        slug = slugify(title)
        coll, c_created = Collections.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "sub_title": sub,
                "description": desc,
                "user": admin
            }
        )
        seeded_collections.append(coll)
        print(f"Collection: {coll.title} (Created: {c_created})")

    # 5. Seed 5 BlogPosts & BlogMedia
    blog_data = [
        (
            "5 Tips for Capturing Perfect Digital Body Measurements",
            "A step-by-step guide for tailors and clients to capture measurements accurately using mobile devices.",
            "Capturing body measurements digitally requires precision. Follow this simple guide to ensure a flawless custom fit for your next traditional outfit."
        ),
        (
            "The Evolution of Agbada: From Tradition to Modern Luxury",
            "An exploration of how the Grand Agbada has transitioned from classical wear to modern runways.",
            "The Agbada has always been a symbol of wealth and prestige. In 2026, designers are modernizing this timeless silhouette with lightweight cashmere and custom embroidery."
        ),
        (
            "Why Custom Tailoring is Worth the Investment",
            "Understanding the quality, fit, and sustainability benefits of bespoke tailoring vs mass-produced garments.",
            "Off-the-rack clothing rarely fits perfectly. Investing in a professional tailor ensures your garment is crafted specifically for your unique measurements, using high-quality materials."
        ),
        (
            "Fabric Selection Guide: Choosing the Right Lace for Your Gown",
            "A comprehensive overview of French, Cord, and George lace types for ceremonial bridal wear.",
            "Choosing the right fabric is critical for any custom gown. Learn the differences between Cord, Dry, and organza-based laces to achieve the perfect flow and luxury look."
        ),
        (
            "Connecting with Your Tailor: Best Practices for Direct Chat",
            "How to effectively communicate design ideas, measurement adjustments, and delivery dates.",
            "Clear communication ensures a successful tailoring experience. Use direct chat to send reference styles, confirm details, and schedule fittings."
        )
    ]
    
    for title, excerpt, content in blog_data:
        slug = slugify(title)
        post, p_created = BlogPost.objects.update_or_create(
            slug=slug,
            defaults={
                "title": title,
                "excerpt": excerpt,
                "content": content,
                "status": BlogPostStatus.PUBLISHED,
                "published_at": timezone.now(),
                "author": admin,
                "is_featured": True,
            }
        )
        print(f"Blog Post: {post.title} (Created: {p_created})")
        
        # Attach a BlogMedia item
        media, m_created = BlogMedia.objects.update_or_create(
            post=post,
            sort_order=1,
            defaults={
                "alt_text": f"Cover image for {post.title}",
                "uploaded_by": admin,
            }
        )
        print(f"  Blog Media: {media.alt_text} (Created: {m_created})")

    print("\nCatalog seeding complete!")

if __name__ == "__main__":
    seed()
