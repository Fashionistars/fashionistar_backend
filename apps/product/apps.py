# apps/product/apps.py
from django.apps import AppConfig
from django.utils.translation import gettext_lazy as _


class ProductConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.product"
    verbose_name = _("Product Catalogue")

    def ready(self):
        try:
            import apps.product.signals  # noqa: F401
        except ImportError:
            pass

        try:
            from auditlog.registry import auditlog
            from apps.product.models import (
                Product,
                ProductReview,
                ProductWishlist,
                Coupon,
            )

            auditlog.register(Product, exclude_fields=["search_vector"])
            auditlog.register(ProductReview)
            auditlog.register(ProductWishlist)
            auditlog.register(Coupon)
        except Exception:
            import logging
            logging.getLogger("application").debug(
                "django-auditlog product registration skipped"
            )
