from django.conf import settings

CATEGORY_IMAGE_FALLBACKS = {
    "african-print-ready-to-wear-rtw": "https://images.unsplash.com/photo-1595777457583-95e059d581b8?w=600&auto=format&fit=crop&q=80",
    "grand-agbadas-ceremonial-wear": "https://images.unsplash.com/photo-1617627143750-d86bc21e42bb?w=600&auto=format&fit=crop&q=80",
    "haute-couture-lace-aso-ebi": "https://images.unsplash.com/photo-1566174053879-31528523f8ae?w=600&auto=format&fit=crop&q=80",
    "luxury-bridal-custom-gowns": "https://images.unsplash.com/photo-1594552072238-b8a33785b261?w=600&auto=format&fit=crop&q=80",
    "bespoke-senators-kaftans": "https://images.unsplash.com/photo-1507679799987-c73779587ccf?w=600&auto=format&fit=crop&q=80",
}

def safe_media_url(obj, *field_names: str) -> str:
    for field_name in field_names:
        value = getattr(obj, field_name, None)
        if not value:
            continue
        if isinstance(value, str):
            url = value
        else:
            try:
                url = value.url
            except (AttributeError, ValueError):
                continue
        if url:
            # Check for known category image fallbacks first
            for key, fallback in CATEGORY_IMAGE_FALLBACKS.items():
                if key in url:
                    return fallback
            
            # Map local relative/media paths to a high-quality placeholder in production
            if (url.startswith("/media/") or "catalog/categories/" in url) and not getattr(settings, "DEBUG", False):
                return "https://images.unsplash.com/photo-1483985988355-763728e1935b?w=600&auto=format&fit=crop&q=80"

            # Auto-inject Cloudinary optimal transformations (q_auto, f_auto)
            if "res.cloudinary.com" in url and "/upload/" in url:
                return url.replace("/upload/", "/upload/f_auto,q_auto/")
            return url
    return ""
