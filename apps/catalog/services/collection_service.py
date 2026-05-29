# apps/catalog/services/collection_service.py


class CollectionService:
    """Write service for merchandising collections."""

    resource_type = "catalog.collection"

    @classmethod
    def create(cls, *, serializer, request):
        user = getattr(request, "user", None)
        instance = serializer.save(user=user if getattr(user, "is_authenticated", False) else None)

        from apps.audit_logs.services.catalog import catalog_audit
        from django.db import transaction

        def _dispatch():
            try:
                catalog_audit.log_collection_created(
                    actor=user,
                    collection_id=str(instance.pk),
                    name=instance.name,
                    request=request,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"CollectionService.create: Audit failed: {e}")

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
                catalog_audit.log_collection_updated(
                    actor=user,
                    collection_id=str(instance.pk),
                    name=instance.name,
                    old_values=old_values,
                    new_values=serializer.data,
                    request=request,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"CollectionService.update: Audit failed: {e}")

        transaction.on_commit(_dispatch)
        return instance

    @classmethod
    def archive(cls, *, instance, request, old_values: dict):
        instance.soft_delete()

        from apps.audit_logs.services.catalog import catalog_audit
        from django.db import transaction

        def _dispatch():
            try:
                # Use updated for archive as well, or I could add log_collection_archived
                catalog_audit.log_collection_updated(
                    actor=getattr(request, "user", None),
                    collection_id=str(instance.pk),
                    name=instance.name,
                    old_values=old_values,
                    new_values={"archive_requested": True},
                    request=request,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"CollectionService.archive: Audit failed: {e}")

        transaction.on_commit(_dispatch)
        return instance
