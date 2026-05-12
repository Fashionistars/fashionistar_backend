from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Fashionistar Catalog"

    def ready(self):
        super().ready()

        # ── 1. Auditlog registration ────────────────────────────────────────────
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

        # ── 2. Redis cache-invalidation signal ─────────────────────────────────
        #
        # Fires on every save/delete of any catalog model from the Django admin
        # or any service layer call.  Invalidates the entire catalog:* key
        # namespace so that the next Ninja async request re-populates the cache
        # from the DB rather than returning stale data.
        #
        # Pattern used:  api_cache_delete_pattern("catalog:*")
        # This covers:
        #   • catalog:categories:{page}:{page_size}
        #   • catalog:brands:{page}:{page_size}
        #   • catalog:collections:{page}:{page_size}
        #   • catalog:blog:{page}:{page_size}
        #
        # Design: the handler is intentionally fail-safe. A Redis outage must
        # NEVER raise an exception that would abort an admin save() operation.
        # ──────────────────────────────────────────────────────────────────────
        try:
            from django.db.models.signals import post_delete, post_save

            from apps.catalog.models import BlogMedia, BlogPost, Brand, Category, Collections
            from apps.catalog.signals import invalidate_catalog_cache

            _CATALOG_MODELS = (Brand, Category, Collections, BlogPost, BlogMedia)
            _dispatch_uid_prefix = "catalog_cache_bust"

            for _model in _CATALOG_MODELS:
                post_save.connect(
                    invalidate_catalog_cache,
                    sender=_model,
                    dispatch_uid=f"{_dispatch_uid_prefix}_save_{_model.__name__}",
                    weak=False,
                )
                post_delete.connect(
                    invalidate_catalog_cache,
                    sender=_model,
                    dispatch_uid=f"{_dispatch_uid_prefix}_delete_{_model.__name__}",
                    weak=False,
                )

        except Exception:
            import logging

            logging.getLogger("application").debug(
                "catalog cache-bust signal registration skipped"
            )
