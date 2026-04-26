from apps.catalog.services.catalog_service import CatalogAuditService


class BlogService:
    """Write service for catalog blog posts."""

    resource_type = "catalog.blog"

    @classmethod
    def create(cls, *, serializer, request):
        user = getattr(request, "user", None)
        instance = serializer.save(author=user if getattr(user, "is_authenticated", False) else None)
        CatalogAuditService.log_mutation(
            request=request,
            action="catalog.blog.created",
            resource_type=cls.resource_type,
            resource_id=instance.pk,
            new_values=serializer.data,
        )
        return instance

    @classmethod
    def update(cls, *, serializer, request, old_values: dict):
        instance = serializer.save()
        CatalogAuditService.log_mutation(
            request=request,
            action="catalog.blog.updated",
            resource_type=cls.resource_type,
            resource_id=instance.pk,
            old_values=old_values,
            new_values=serializer.data,
        )
        return instance

    @classmethod
    def archive(cls, *, instance, request, old_values: dict):
        instance.soft_delete()
        CatalogAuditService.log_mutation(
            request=request,
            action="catalog.blog.archived",
            resource_type=cls.resource_type,
            resource_id=instance.pk,
            old_values=old_values,
            new_values={"is_deleted": True},
        )
        return instance
