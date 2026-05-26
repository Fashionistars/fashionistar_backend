# scratch/seed_production_catalog_premium.py
import os
import sys
import django
from django.utils import timezone
from django.utils.text import slugify

# Setup Django environment
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "backend.config.development")
django.setup()

import cloudinary.uploader
from django.contrib.auth import get_user_model
from apps.catalog.models import Category, Brand, Collections, BlogPost, BlogMedia, BlogPostStatus

User = get_user_model()

# Base paths
FRONTEND_PUBLIC_DIR = "c:\\Users\\FASHIONISTAR\\OneDrive\\Documenti\\FASHIONISTAR_ANTAGRAVITY\\fashionista_frontend\\public"

def upload_to_cloudinary(local_rel_path, fallback_url, folder, public_id_base=None):
    """
    Attempts to upload the local asset if it exists. If not, falls back to the 4K Unsplash URL.
    Returns the Cloudinary upload result.
    """
    # Build local path
    local_path = None
    if local_rel_path:
        local_path = os.path.join(FRONTEND_PUBLIC_DIR, local_rel_path.replace("/", "\\"))
    
    upload_target = fallback_url
    is_local = False
    
    if local_path and os.path.exists(local_path) and os.path.isfile(local_path):
        upload_target = local_path
        is_local = True
        print(f"  [Local Asset Found] Using local file: {local_path}")
    else:
        print(f"  [Local Asset Not Found / Skipping] Falling back to 4K internet URL: {fallback_url}")
        
    # Configure upload options
    options = {
        "folder": folder,
        "overwrite": True,
        "resource_type": "image"
    }
    if public_id_base:
        options["public_id"] = slugify(public_id_base)
        
    try:
        print(f"  [Cloudinary Sync] Uploading to folder '{folder}'...")
        res = cloudinary.uploader.upload(upload_target, **options)
        print(f"  [Cloudinary Sync Success] Public ID: {res['public_id']} | URL: {res['secure_url']}")
        return res
    except Exception as e:
        print(f"  [Cloudinary Sync FAILED] Error: {e}")
        # In case of local upload failure (e.g. format issues), try direct URL fallback
        if is_local:
            try:
                print(f"  [Cloudinary Sync Retrying] Attempting fallback to 4K URL: {fallback_url}")
                res = cloudinary.uploader.upload(fallback_url, **options)
                print(f"  [Cloudinary Sync Success] Fallback Public ID: {res['public_id']}")
                return res
            except Exception as e2:
                print(f"  [Cloudinary Sync Fallback FAILED] Error: {e2}")
        return None

def seed_production_catalog():
    print("================================================================================")
    print("🚀 FASHIONISTAR: ENTERPRISE PRODUCTION STOREFRONT SEEDING STARTING NOW")
    print("================================================================================")
    
    # 1. Fetch or create Admin User context
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
    admin.is_active = True
    admin.save()
    print(f"✓ Admin User context settled: {admin.email} (Superuser: {admin.is_superuser})")
    
    # 2. Cleanup legacy / test entries to prevent constraint conflicts and ensure a pristine launch state
    print("Cleaning up legacy storefront database records...")
    BlogMedia.objects.all().delete()
    BlogPost.objects.all().delete()
    Collections.objects.all().delete()
    Brand.objects.all().delete()
    Category.objects.all().delete()
    print("✓ Storefront database cleared of legacy dummy models.")
    
    # 3. Seed 5 Categories
    print("\n--- Seeding 5 Catalog Categories (Product Creation Selections) ---")
    categories_data = [
        {
            "name": "Haute Couture Lace & Aso Ebi",
            "desc": "Opulent hand-beaded lace, custom embroidery, and traditional Aso Ebi styles curated for elite celebrations.",
            "local": "products/WhatsApp Image 2024-06-04 at 13.33.35.jpeg",
            "url": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?q=80&w=1200"
        },
        {
            "name": "Bespoke Senators & Kaftans",
            "desc": "Precision-cut linen and cashmere senator suits, long-sleeve kaftans, and minimal daily tunics.",
            "local": "man.png",
            "url": "https://images.unsplash.com/photo-1617137968427-85924c800a22?q=80&w=1200"
        },
        {
            "name": "Grand Agbadas & Ceremonial Wear",
            "desc": "Masterfully hand-embroidered grand Agbadas and formal robes crafted for modern royalty.",
            "local": "products/WhatsApp Image 2024-06-04 at 13.33.35 (1).jpeg",
            "url": "https://images.unsplash.com/photo-1607823024191-c1675fb4e2e2?q=80&w=1200"
        },
        {
            "name": "African Print Ready-to-Wear (RTW)",
            "desc": "Vibrant premium Ankara jumpsuits, dresses, and contemporary coordinate sets ready for immediate dispatch.",
            "local": "adunni.png",
            "url": "https://images.unsplash.com/photo-1560769629-975ec94e6a86?q=80&w=1200"
        },
        {
            "name": "Luxury Bridal & Custom Gowns",
            "desc": "Custom bespoke wedding gowns, reception masterpieces, and luxury evening wear tailored to absolute precision.",
            "local": "products/WhatsApp Image 2024-06-04 at 13.33.34.jpeg",
            "url": "https://images.unsplash.com/photo-1594552072238-b8a33785b261?q=80&w=1200"
        }
    ]
    
    seeded_categories = {}
    for cat_data in categories_data:
        name = cat_data["name"]
        print(f"Creating Category: '{name}'")
        res = upload_to_cloudinary(
            cat_data["local"],
            cat_data["url"],
            "fashionistar/catalog/categories/",
            public_id_base=name
        )
        
        cat = Category.objects.create(
            name=name,
            active=True,
            user=admin
        )
        if res:
            cat.image = res["public_id"]
            cat.save()
            
        seeded_categories[name] = cat
        print(f"  ✓ Saved Category ID: {cat.pk} | Slug: {cat.slug}\n")
        
    # 4. Seed 5 Brands
    print("\n--- Seeding 5 Catalog Brands (Fashionistar Partners) ---")
    brands_data = [
        {
            "title": "Deola Sagoe",
            "desc": "The pioneer of Nigerian haute couture, renowned for structural Komole designs and Yoruba textile innovations.",
            "local": "pics.png",
            "url": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?q=80&w=1200"
        },
        {
            "title": "Mai Atafo",
            "desc": "World-class Savile Row-inspired tailoring, bespoke suits, and exquisite modern wedding couture.",
            "local": "ceo.png",
            "url": "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?q=80&w=1200"
        },
        {
            "title": "Adebayo Jones Couture",
            "desc": "The definition of elegance, luxury fabrics, and sweeping ceremonial drapes tailored to global perfection.",
            "local": "heroimg.png",
            "url": "https://images.unsplash.com/photo-1512436991641-6745cdb1723f?q=80&w=1200"
        },
        {
            "title": "Tiffany Amber",
            "desc": "Luxurious resort styling, flowy silk coordinates, and contemporary luxury ready-to-wear.",
            "local": "girl.png",
            "url": "https://images.unsplash.com/photo-1509631179647-0177331693ae?q=80&w=1200"
        },
        {
            "title": "Orange Culture",
            "desc": "Award-winning avant-garde design house blending traditional fabric heritage with gender-neutral streetwear.",
            "local": "empty.svg",
            "url": "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?q=80&w=1200"
        }
    ]
    
    for brand_data in brands_data:
        title = brand_data["title"]
        print(f"Creating Brand: '{title}'")
        res = upload_to_cloudinary(
            brand_data["local"],
            brand_data["url"],
            "fashionistar/catalog/brands/",
            public_id_base=title
        )
        
        brand = Brand.objects.create(
            title=title,
            description=brand_data["desc"],
            active=True,
            user=admin
        )
        if res:
            brand.image = res["public_id"]
            brand.save()
            
        print(f"  ✓ Saved Brand ID: {brand.pk} | Slug: {brand.slug}\n")
        
    # 5. Seed 5 Collections
    print("\n--- Seeding 5 Catalog Collections (Vendor Profiles Selections) ---")
    collections_data = [
        {
            "title": "Sovereign Dynasty",
            "sub_title": "Royal ceremonial attire for modern elites.",
            "desc": "Deep hues, heavy embroidery, and regal cuts crafted by FASHIONISTAR master tailors.",
            "local_main": "products/WhatsApp Image 2024-06-01 at 20.15.58.jpeg",
            "url_main": "https://images.unsplash.com/photo-1582533561751-ef6f6ab93a2e?q=80&w=1200",
            "url_bg": "https://images.unsplash.com/photo-1560769629-975ec94e6a86?q=80&w=1920"
        },
        {
            "title": "Sahara Breeze Resort",
            "sub_title": "Minimalist linen and lightweight luxury.",
            "desc": "Flowing resort wear, breathable senators, and soft kaftans designed for warm-weather sophisticated comfort.",
            "local_main": "products/WhatsApp Image 2024-06-02 at 23.12.20.jpeg",
            "url_main": "https://images.unsplash.com/photo-1605497746444-051f38e2d45c?q=80&w=1200",
            "url_bg": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?q=80&w=1920"
        },
        {
            "title": "Elegance of Aso-Oke",
            "sub_title": "Modern expressions of handwoven heritage.",
            "desc": "Structured modern gowns, vests, and jackets woven from premium Yoruba Aso-Oke fabrics.",
            "local_main": "products/WhatsApp Image 2024-06-04 at 13.33.36 (1).jpeg",
            "url_main": "https://images.unsplash.com/photo-1590075865003-e48277faa558?q=80&w=1200",
            "url_bg": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?q=80&w=1920"
        },
        {
            "title": "Lagos Cyberpunk Streetwear",
            "sub_title": "Avant-garde urban prints.",
            "desc": "High-contrast prints blended with modern athletic shapes and functional designer accessories.",
            "local_main": "man.png",
            "url_main": "https://images.unsplash.com/photo-1509631179647-0177331693ae?q=80&w=1200",
            "url_bg": "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?q=80&w=1920"
        },
        {
            "title": "Monarch Bridal Romance",
            "sub_title": "Handcrafted bespoke bridal wear.",
            "desc": "Gowns and reception wear featuring delicate lace overlays, custom beadwork, and sweeping trains.",
            "local_main": "products/WhatsApp Image 2024-06-04 at 13.33.34.jpeg",
            "url_main": "https://images.unsplash.com/photo-1594552072238-b8a33785b261?q=80&w=1200",
            "url_bg": "https://images.unsplash.com/photo-1549417229-aa67d3263c09?q=80&w=1920"
        }
    ]
    
    for coll_data in collections_data:
        title = coll_data["title"]
        print(f"Creating Collection: '{title}'")
        
        # Upload main image
        print("  [Main Image Sync]")
        res_main = upload_to_cloudinary(
            coll_data["local_main"],
            coll_data["url_main"],
            "fashionistar/catalog/collections/",
            public_id_base=f"{title}_main"
        )
        
        # Upload background image
        print("  [Background Image Sync]")
        res_bg = upload_to_cloudinary(
            None,
            coll_data["url_bg"],
            "fashionistar/catalog/collections/backgrounds/",
            public_id_base=f"{title}_bg"
        )
        
        coll = Collections.objects.create(
            title=title,
            sub_title=coll_data["sub_title"],
            description=coll_data["desc"],
            user=admin
        )
        if res_main:
            coll.image = res_main["public_id"]
        if res_bg:
            coll.background_image = res_bg["public_id"]
        coll.save()
        
        print(f"  ✓ Saved Collection ID: {coll.pk} | Slug: {coll.slug}\n")
        
    # 6. Seed 5 BlogPosts & BlogMedia Inlines
    print("\n--- Seeding 5 Catalog BlogPosts & Gallery Media (Editorial Discovery) ---")
    blogs_data = [
        {
            "title": "The Art of Bespoke: Why Digital Body Scanning is the Future",
            "category": "Bespoke Senators & Kaftans",
            "excerpt": "Discover how digital precision eliminates multiple fittings and connects you with tailors globally.",
            "content": "Bespoke tailoring has always been the gold standard of fashion, especially across West Africa. However, the traditional process required multiple in-person fittings, limiting clients to tailors in their immediate local vicinity. With FASHIONISTAR's advanced 3D digital body scanning ecosystem, that limit is completely shattered. Clients can capture their precise body parameters in seconds using a smartphone camera, creating a secure digital profile. Master tailors on the other side of the world can then access this data, translate it into standard fabric patterns, and stitch garments with millimeter accuracy. In this editorial, we sit down with leading tailors to discuss how digital precision is boosting business and guaranteeing a perfect, stress-free custom fit every single time.",
            "featured_url": "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?q=80&w=1200",
            "gallery": [
                {"alt": "Advanced digital measurements and tailoring blueprint", "url": "https://images.unsplash.com/photo-1485827404703-89b55fcc595e?q=80&w=1200"},
                {"alt": "Tailor reviewing body scan data profile", "url": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?q=80&w=1200"}
            ]
        },
        {
            "title": "The Modern Agbada: How Millennial Designers Redefined the Silhouette",
            "category": "Grand Agbadas & Ceremonial Wear",
            "excerpt": "Traditional volume meets contemporary fabric innovation as designers transform the ceremonial classic.",
            "content": "The Agbada has historically stood as the ultimate symbol of wealth, majesty, and masculine grace in West African culture. Traditionally heavy and vast, it demanded significant physical posture to carry. Today, a new wave of millennial designers is redefining this iconic silhouette for the modern urban environment. By utilizing exceptionally lightweight cashmere, breathable Irish linens, and intricate minimalistic hand-embroidery, these designers are creating Agbadas that offer structural majesty without the cumbersome weight. In this feature, we look at the rising runway trends, styling options (combining Agbadas with sleek Chelsea boots or premium leather slides), and how FASHIONISTAR enables clients to design and customize their own royal robes remotely.",
            "featured_url": "https://images.unsplash.com/photo-1607823024191-c1675fb4e2e2?q=80&w=1200",
            "gallery": [
                {"alt": "Sleek cashmere drape traditional style", "url": "https://images.unsplash.com/photo-1582533561751-ef6f6ab93a2e?q=80&w=1200"},
                {"alt": "Young male model showing modern navy kaftan Agbada", "url": "https://images.unsplash.com/photo-1617137968427-85924c800a22?q=80&w=1200"}
            ]
        },
        {
            "title": "Understanding Luxury Lace: A Guide to French, Cord, and George Laces",
            "category": "Haute Couture Lace & Aso Ebi",
            "excerpt": "Elevate your Aso Ebi styling by selecting the perfect high-grade textile weave for your designer cuts.",
            "content": "No high-end traditional wedding or grand ceremony is complete without the visual splendor of luxury lace. But with a market flooded with varying grades of fabric, how do you distinguish truly premium textile weaves? This comprehensive guide breaks down the core luxury laces. From French Solstiss lace with its delicate metallic threads, to thick hand-beaded Cord lace featuring raised dimensional motifs, and heavy silk George lace woven with gold patterns, we outline the composition, drape, and ideal styling structure for each. We also share master tips on sewing lining fabrics to accentuate the lace's organic skin-transparency patterns for stunning, red-carpet ready Aso Ebi silhouettes.",
            "featured_url": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?q=80&w=1200",
            "gallery": [
                {"alt": "Intricate hand-stitched beadwork detailing on luxury lace", "url": "https://images.unsplash.com/photo-1590075865003-e48277faa558?q=80&w=1200"},
                {"alt": "Bespoke wedding gown overlay fabric details", "url": "https://images.unsplash.com/photo-1594552072238-b8a33785b261?q=80&w=1200"}
            ]
        },
        {
            "title": "Optimizing Your Measurement Profile: Achieve a Flawless Custom Fit Every Time",
            "category": "Bespoke Senators & Kaftans",
            "excerpt": "Master our simple scanning system to ensure your tailoring commands are followed with millimeter accuracy.",
            "content": "The cornerstone of any great custom garment is the accuracy of its measurement data. At FASHIONISTAR, our engineering team has designed a highly sophisticated yet incredibly simple mobile-friendly measurement capture flow. In this tutorial, we provide step-by-step guidance on how to optimize your digital scanning session. Learn the ideal room lighting conditions, the best close-fitting clothing to wear during a scan, and how to stand to capture your natural posture. By following these easy guidelines, you will create a highly precise digital body double that tailors can use to achieve an immaculate custom fit without a single physical measuring tape touching your skin.",
            "featured_url": "https://images.unsplash.com/photo-1556742049-0cfed4f6a45d?q=80&w=1200",
            "gallery": [
                {"alt": "Millimeter-precise tailoring patterns and adjustments", "url": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?q=80&w=1200"},
                {"alt": "Sleek tech interface mapping user body contours", "url": "https://images.unsplash.com/photo-1581091226825-a6a2a5aee158?q=80&w=1200"}
            ]
        },
        {
            "title": "FASHIONISTAR Chronicles: Connecting Global Clients with African Master Tailors",
            "category": "African Print Ready-to-Wear (RTW)",
            "excerpt": "Meet the artisans behind the platform who bring bespoke African high-fashion straight to your doorstep.",
            "content": "FASHIONISTAR is more than just a software platform; it is a global bridge of culture and craftsmanship. Across major African cities—from the bustling design quarters of Yaba in Lagos, to Osu in Accra, and the creative hubs of Dakar—extraordinary master tailors have preserved textile art secrets for generations. Our platform empowers these highly skilled artisans by connecting them with fashion enthusiasts worldwide. We handle secure payments, coordinate automated sizing data, and facilitate expedited international logistics. Today, we share the inspiring stories of three FASHIONISTAR tailors who have grown their local operations into thriving global export brands, showcasing the luxury of African fashion to the world.",
            "featured_url": "https://images.unsplash.com/photo-1492562080023-ab3db95bfbce?q=80&w=1200",
            "gallery": [
                {"alt": "Designer sketching avant-garde streetwear silhouettes", "url": "https://images.unsplash.com/photo-1529139574466-a303027c1d8b?q=80&w=1200"},
                {"alt": "Finished premium African print high-fashion collection display", "url": "https://images.unsplash.com/photo-1596462502278-27bfdc403348?q=80&w=1200"}
            ]
        }
    ]
    
    for blog_data in blogs_data:
        title = blog_data["title"]
        print(f"Creating Blog Post: '{title}'")
        
        # Upload featured image
        res_featured = upload_to_cloudinary(
            None,
            blog_data["featured_url"],
            "fashionistar/catalog/blog/featured/",
            public_id_base=f"{title}_feat"
        )
        
        # Match Category
        category_name = blog_data["category"]
        cat_instance = seeded_categories.get(category_name)
        
        # Construct tags & SEO fields
        tags = [t.lower() for t in category_name.split() if len(t) > 2]
        seo_title = f"{title} | FASHIONISTAR Editorial"
        seo_desc = blog_data["excerpt"][:320]
        
        post = BlogPost.objects.create(
            title=title,
            category=cat_instance,
            excerpt=blog_data["excerpt"],
            content=blog_data["content"],
            status=BlogPostStatus.PUBLISHED,
            published_at=timezone.now(),
            author=admin,
            is_featured=True,
            tags=tags,
            seo_title=seo_title,
            seo_description=seo_desc
        )
        if res_featured:
            post.featured_image = res_featured["public_id"]
            post.save()
            
        print(f"  ✓ Saved BlogPost ID: {post.pk} | Slug: {post.slug}")
        
        # Attach rich BlogMedia gallery items
        for i, gallery_item in enumerate(blog_data["gallery"]):
            print(f"  Creating Gallery Media {i+1}...")
            res_gal = upload_to_cloudinary(
                None,
                gallery_item["url"],
                "fashionistar/catalog/blog/gallery/",
                public_id_base=f"{title}_gal_{i+1}"
            )
            
            media = BlogMedia.objects.create(
                post=post,
                uploaded_by=admin,
                alt_text=gallery_item["alt"],
                sort_order=i+1
            )
            if res_gal:
                media.image = res_gal["public_id"]
                media.save()
                media.refresh_from_db()
                
            print(f"    ✓ Saved BlogMedia ID: {media.pk} | Url: {media.image_url}")
        print()
        
    print("================================================================================")
    print("🎉 FASHIONISTAR STOREFRONT DATABASE SEEDING COMPLETED SUCCESSFULLY!")
    print("================================================================================")

if __name__ == "__main__":
    seed_production_catalog()
