from apps.admin_backend.models import Brand, Category, Collections


class CatalogSelector:
    """Read-side query helpers for public commerce metadata."""

    @staticmethod
    def categories():
        return (
            Category.objects.filter(active=True)
            .only("id", "name", "slug", "image", "cloudinary_url", "active", "created_at", "updated_at")
            .order_by("name")
        )

    @staticmethod
    def brands():
        return (
            Brand.objects.filter(active=True)
            .only("id", "title", "slug", "description", "image", "cloudinary_url", "active", "created_at", "updated_at")
            .order_by("title")
        )

    @staticmethod
    def collections():
        return (
            Collections.objects.all()
            .only(
                "id",
                "title",
                "slug",
                "sub_title",
                "description",
                "image",
                "cloudinary_url",
                "background_image",
                "background_cloudinary_url",
                "created_at",
                "updated_at",
            )
            .order_by("-created_at")
        )
