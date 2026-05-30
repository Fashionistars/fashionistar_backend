from django.apps import AppConfig


class CatalogConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.catalog"
    label = "catalog"
    verbose_name = "Fashionistar Catalog"

    def ready(self):
        super().ready()

        import logging

        _log = logging.getLogger(__name__)

        # ── 1. Auditlog registration ───────────────────────────────────────────
        try:
            from auditlog.registry import auditlog  # type: ignore[import]

            from apps.catalog.models import (
                BlogMedia,
                BlogPost,
                Brand,
                CatalogBanner,
                Category,
                Collections,
                Tag,
            )

            for model in (Brand, Category, Collections, BlogPost, BlogMedia, CatalogBanner, Tag):
                auditlog.register(model)
        except Exception:
            _log.debug("catalog auditlog registration skipped (registry unavailable)")

        # ── 2. EventBus subscription bootstrap ────────────────────────────────
        # All catalog domain events are wired here via EventBus (no raw signal
        # business logic). Handlers live in apps/catalog/events/__init__.py.
        try:
            from apps.catalog.events import subscribe_catalog_events

            subscribe_catalog_events()
        except Exception as exc:
            _log.debug("catalog EventBus subscription skipped: %s", exc)

        # ── 3. Django signal → EventBus bridge ────────────────────────────────
        # Connects Django ORM post_save / post_delete signals to the EventBus
        # bridge functions in apps/catalog/signals.py.
        # Each bridge uses transaction.on_commit() internally.
        try:
            from django.db.models.signals import post_delete, post_save

            from apps.catalog.models import (
                BlogPost,
                Brand,
                CatalogBanner,
                Category,
                Collections,
            )
            from apps.catalog.signals import (
                invalidate_catalog_cache,
                on_banner_post_delete,
                on_banner_post_save,
                on_blog_post_save,
                on_brand_post_save,
                on_category_post_delete,
                on_category_post_save,
                on_collection_post_save,
            )

            _pfx = "catalog"

            # ── Generic cache-bust for all catalog models ──────────────────────
            _ALL_MODELS = (Brand, Category, Collections, BlogPost, CatalogBanner)
            for _m in _ALL_MODELS:
                post_save.connect(
                    invalidate_catalog_cache,
                    sender=_m,
                    dispatch_uid=f"{_pfx}_cache_save_{_m.__name__}",
                    weak=False,
                )
                post_delete.connect(
                    invalidate_catalog_cache,
                    sender=_m,
                    dispatch_uid=f"{_pfx}_cache_delete_{_m.__name__}",
                    weak=False,
                )

            # ── Specific EventBus bridge signals ──────────────────────────────
            post_save.connect(
                on_category_post_save,
                sender=Category,
                dispatch_uid=f"{_pfx}_eventbus_save_category",
                weak=False,
            )
            post_delete.connect(
                on_category_post_delete,
                sender=Category,
                dispatch_uid=f"{_pfx}_eventbus_delete_category",
                weak=False,
            )
            post_save.connect(
                on_brand_post_save,
                sender=Brand,
                dispatch_uid=f"{_pfx}_eventbus_save_brand",
                weak=False,
            )
            post_save.connect(
                on_collection_post_save,
                sender=Collections,
                dispatch_uid=f"{_pfx}_eventbus_save_collection",
                weak=False,
            )
            post_save.connect(
                on_banner_post_save,
                sender=CatalogBanner,
                dispatch_uid=f"{_pfx}_eventbus_save_banner",
                weak=False,
            )
            post_delete.connect(
                on_banner_post_delete,
                sender=CatalogBanner,
                dispatch_uid=f"{_pfx}_eventbus_delete_banner",
                weak=False,
            )
            post_save.connect(
                on_blog_post_save,
                sender=BlogPost,
                dispatch_uid=f"{_pfx}_eventbus_save_blog",
                weak=False,
            )

            _log.debug("Catalog signal bridges registered.")

        except Exception as exc:
            _log.debug("catalog signal registration skipped: %s", exc)
