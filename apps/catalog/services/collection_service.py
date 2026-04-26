from apps.catalog.services.catalog_service import CatalogAuditService


class CollectionService:
    """Write service for merchandising collections."""

    resource_type = "catalog.collection"

    @classmethod
    def create(cls, *, serializer, request):
        user = getattr(request, "user", None)
        instance = serializer.save(user=user if getattr(user, "is_authenticated", False) else None)
        CatalogAuditService.log_mutation(
            request=request,
            action="catalog.collection.created",
            resource_type=cls.resource_type,
            resource_id=instance.pk,
            new_values=serializer.data,
        )
        return instance

    @classmethod
    def update(cls, *, serializer, request, old_values: dict):
        user = getattr(request, "user", None)
        instance = serializer.save(user=user if getattr(user, "is_authenticated", False) else None)
        CatalogAuditService.log_mutation(
            request=request,
            action="catalog.collection.updated",
            resource_type=cls.resource_type,
            resource_id=instance.pk,
            old_values=old_values,
            new_values=serializer.data,
        )
        return instance

    @classmethod
    def archive(cls, *, instance, request, old_values: dict):
        instance.cloudinary_url = instance.cloudinary_url or ""
        instance.save(update_fields=["cloudinary_url", "updated_at"])
        CatalogAuditService.log_mutation(
            request=request,
            action="catalog.collection.archive_requested",
            resource_type=cls.resource_type,
            resource_id=instance.pk,
            old_values=old_values,
            new_values={"archive_requested": True},
        )
        return instance
