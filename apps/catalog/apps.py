from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Fashionistar Catalog"

    def ready(self):
        super().ready()
        try:
            from auditlog.registry import auditlog

            from apps.catalog.models import BlogMedia, BlogPost, Brand, Category, Collections

            for model in (Brand, Category, Collections, BlogPost, BlogMedia):
                auditlog.register(model)
        except Exception:
            import logging

            logging.getLogger("application").debug(
                "catalog auditlog registration skipped (registry unavailable)"
            )
