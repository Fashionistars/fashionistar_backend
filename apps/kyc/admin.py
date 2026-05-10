"""KYC admin registration."""

from django.contrib import admin

from apps.kyc.models import KycDocument, KycSubmission


class KycDocumentInline(admin.TabularInline):
    """Inline read view of identity document references."""

    model = KycDocument
    extra = 0
    readonly_fields = ("created_at", "updated_at", "provider_verified")
    fields = (
        "document_type",
        "document_number",
        "public_id",
        "secure_url",
        "provider_verified",
        "created_at",
    )


@admin.register(KycSubmission)
class KycSubmissionAdmin(admin.ModelAdmin):
    """Operational review surface for KYC submissions."""

    list_display = ("user", "status", "submitted_at", "reviewed_at", "updated_at")
    list_filter = ("status", "submitted_at", "reviewed_at")
    search_fields = ("user__email", "user__phone", "provider_reference")
    readonly_fields = ("created_at", "updated_at", "submitted_at")
    inlines = [KycDocumentInline]


@admin.register(KycDocument)
class KycDocumentAdmin(admin.ModelAdmin):
    """Standalone document audit surface."""

    list_display = ("submission", "document_type", "provider_verified", "created_at")
    list_filter = ("document_type", "provider_verified", "created_at")
    search_fields = ("submission__user__email", "public_id")
    readonly_fields = ("created_at", "updated_at")
