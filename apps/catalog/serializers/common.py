def safe_media_url(obj, *field_names: str) -> str:
    for field_name in field_names:
        value = getattr(obj, field_name, None)
        if not value:
            continue
        if isinstance(value, str):
            return value
        try:
            url = value.url
        except (AttributeError, ValueError):
            continue
        if url:
            return url
    return ""
