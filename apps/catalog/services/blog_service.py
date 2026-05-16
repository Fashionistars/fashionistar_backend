# apps/catalog/services/blog_service.py


class BlogService:
    """Write service for catalog blog posts."""

    resource_type = "catalog.blog"

    @classmethod
    def create(cls, *, serializer, request):
        user = getattr(request, "user", None)
        instance = serializer.save(author=user if getattr(user, "is_authenticated", False) else None)

        from apps.audit_logs.services.catalog import catalog_audit
        from django.db import transaction

        def _dispatch():
            try:
                catalog_audit.log_blog_post_created(
                    actor=user,
                    post_id=str(instance.pk),
                    title=instance.title,
                    request=request,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"BlogService.create: Audit failed: {e}")

        transaction.on_commit(_dispatch)
        return instance

    @classmethod
    def update(cls, *, serializer, request, old_values: dict):
        instance = serializer.save()

        from apps.audit_logs.services.catalog import catalog_audit
        from django.db import transaction

        def _dispatch():
            try:
                catalog_audit.log_blog_post_updated(
                    actor=getattr(request, "user", None),
                    post_id=str(instance.pk),
                    title=instance.title,
                    old_values=old_values,
                    new_values=serializer.data,
                    request=request,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"BlogService.update: Audit failed: {e}")

        transaction.on_commit(_dispatch)
        return instance

    @classmethod
    def archive(cls, *, instance, request, old_values: dict):
        instance.soft_delete()

        from apps.audit_logs.services.catalog import catalog_audit
        from django.db import transaction

        def _dispatch():
            try:
                catalog_audit.log_blog_post_updated(
                    actor=getattr(request, "user", None),
                    post_id=str(instance.pk),
                    title=instance.title,
                    old_values=old_values,
                    new_values={"is_deleted": True},
                    request=request,
                )
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(f"BlogService.archive: Audit failed: {e}")

        transaction.on_commit(_dispatch)
        return instance
