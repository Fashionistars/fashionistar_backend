from apps.catalog.services.catalog_service import CatalogAuditService


class BrandService:
    """Write service for catalog brands. Serializer validation must already have passed."""

    resource_type = "catalog.brand"

    @classmethod
    def create(cls, *, serializer, request):
        user = getattr(request, "user", None)
        instance = serializer.save(user=user if getattr(user, "is_authenticated", False) else None)
        CatalogAuditService.log_mutation(
            request=request,
            action="catalog.brand.created",
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
            action="catalog.brand.updated",
            resource_type=cls.resource_type,
            resource_id=instance.pk,
            old_values=old_values,
            new_values=serializer.data,
        )
        return instance

    @classmethod
    def archive(cls, *, instance, request, old_values: dict):
        instance.active = False
        instance.save(update_fields=["active", "updated_at"])
        CatalogAuditService.log_mutation(
            request=request,
            action="catalog.brand.archived",
            resource_type=cls.resource_type,
            resource_id=instance.pk,
            old_values=old_values,
            new_values={"active": False},
        )
        return instance
