# apps/catalog/services/category_service.py


class CategoryService:
    """Write service for catalog categories. Serializer validation must already have passed."""

    resource_type = "catalog.category"

    @classmethod
    def create(cls, *, serializer, request):
        user = getattr(request, "user", None)
        instance = serializer.save(user=user if getattr(user, "is_authenticated", False) else None)

        from apps.audit_logs.services.catalog import catalog_audit
        from django.db import transaction

        def _dispatch():
            try:
                catalog_audit.log_category_created(
                    actor=user,
                    category_id=str(instance.pk),
                    name=instance.name,
                    request=request,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"CategoryService.create: Audit failed: {e}")

        transaction.on_commit(_dispatch)
        return instance

    @classmethod
    def update(cls, *, serializer, request, old_values: dict):
        user = getattr(request, "user", None)
        instance = serializer.save(user=user if getattr(user, "is_authenticated", False) else None)

        from apps.audit_logs.services.catalog import catalog_audit
        from django.db import transaction

        def _dispatch():
            try:
                catalog_audit.log_category_updated(
                    actor=user,
                    category_id=str(instance.pk),
                    name=instance.name,
                    old_values=old_values,
                    new_values=serializer.data,
                    request=request,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"CategoryService.update: Audit failed: {e}")

        transaction.on_commit(_dispatch)
        return instance

    @classmethod
    def archive(cls, *, instance, request, old_values: dict):
        instance.active = False
        instance.save(update_fields=["active", "updated_at"])

        from apps.audit_logs.services.catalog import catalog_audit
        from django.db import transaction

        def _dispatch():
            try:
                catalog_audit.log_category_updated(
                    actor=getattr(request, "user", None),
                    category_id=str(instance.pk),
                    name=instance.name,
                    old_values=old_values,
                    new_values={"active": False},
                    request=request,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"CategoryService.archive: Audit failed: {e}")

        transaction.on_commit(_dispatch)
        return instance
