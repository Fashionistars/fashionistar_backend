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
            # Advice 1: Auto-inject Cloudinary optimal transformations (q_auto, f_auto)
            if "res.cloudinary.com" in url and "/upload/" in url:
                return url.replace("/upload/", "/upload/f_auto,q_auto/")
            return url
    return ""
