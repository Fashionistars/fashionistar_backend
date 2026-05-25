"""KYC admin registration — with approve/reject admin actions."""

from django.contrib import admin
from django.contrib import messages
from django.db import transaction
from django.utils.html import format_html

from apps.kyc.models import KycDocument, KycSubmission


class KycDocumentInline(admin.TabularInline):
    """Inline read view of identity document references."""

    model = KycDocument
    extra = 0
    readonly_fields = (
        "document_type",
        "document_number",
        "public_id",
        "secure_url_link",
        "provider_verified",
        "created_at",
    )
    fields = (
        "document_type",
        "document_number",
        "secure_url_link",
        "provider_verified",
        "created_at",
    )

    def secure_url_link(self, obj):
        if obj.secure_url:
            return format_html(
                '<a href="{}" target="_blank" rel="noopener noreferrer">View Document ↗</a>',
                obj.secure_url,
            )
        return "—"
    secure_url_link.short_description = "Document URL"  # type: ignore[attr-defined]


@admin.register(KycSubmission)
class KycSubmissionAdmin(admin.ModelAdmin):
    """Operational review surface for KYC submissions."""

    list_display = (
        "user",
        "status",
        "legal_name",
        "submitted_at",
        "reviewed_at",
        "updated_at",
    )
    list_filter = ("status", "submitted_at", "reviewed_at")
    search_fields = ("user__email", "user__phone", "provider_reference", "legal_name")
    readonly_fields = (
        "user",
        "created_at",
        "updated_at",
        "submitted_at",
        "provider_reference",
    )
    fields = (
        "user",
        "status",
        "legal_name",
        "review_notes",
        "provider_reference",
        "submitted_at",
        "reviewed_at",
        "created_at",
        "updated_at",
    )
    inlines = [KycDocumentInline]
    actions = ["action_approve_kyc", "action_reject_kyc_resubmit", "action_trigger_legal_name_task"]

    def action_approve_kyc(self, request, queryset):
        """
        Admin action: approve selected KYC submissions.

        Sets status = APPROVED, syncs VendorSetupState.id_verified, and
        triggers the Celery task to auto-populate legal_name from provider
        response JSON.
        """
        from apps.kyc.services import KycService
        approved = 0
        errors = 0
        for submission in queryset:
            try:
                with transaction.atomic():
                    KycService.approve_submission(
                        submission_id=submission.pk,
                        admin_user=request.user,
                    )
                approved += 1
            except Exception as exc:
                self.message_user(
                    request,
                    f"Could not approve {submission.user}: {exc}",
                    level=messages.ERROR,
                )
                errors += 1
        if approved:
            self.message_user(
                request,
                f"✅ {approved} KYC submission(s) approved. "
                "Legal names will be auto-populated by background task within ~30 seconds.",
                level=messages.SUCCESS,
            )
    action_approve_kyc.short_description = "✅ Approve KYC submissions"  # type: ignore[attr-defined]

    def action_reject_kyc_resubmit(self, request, queryset):
        """
        Admin action: reject selected KYC submissions (allow resubmit).
        Note: Use the detail page for custom review_notes.
        """
        from apps.kyc.services import KycService
        rejected = 0
        for submission in queryset:
            try:
                KycService.reject_submission(
                    submission_id=submission.pk,
                    admin_user=request.user,
                    review_notes="Please resubmit with clearer documents. Contact support if you need help.",
                    allow_resubmit=True,
                )
                rejected += 1
            except Exception as exc:
                self.message_user(
                    request,
                    f"Could not reject {submission.user}: {exc}",
                    level=messages.ERROR,
                )
        if rejected:
            self.message_user(
                request,
                f"❌ {rejected} KYC submission(s) rejected (resubmit allowed).",
                level=messages.WARNING,
            )
    action_reject_kyc_resubmit.short_description = "❌ Reject KYC (allow resubmit)"  # type: ignore[attr-defined]

    def action_trigger_legal_name_task(self, request, queryset):
        """
        Admin action: manually trigger legal_name population task for approved submissions.
        Use this if the Celery task missed a submission or legal_name is blank.
        """
        from apps.kyc.tasks import (
            set_legal_name_from_provider_response,
            sync_bank_account_kyc_match,
        )
        from apps.kyc.models.kyc_submission import KycStatus
        triggered = 0
        for submission in queryset:
            if submission.status == KycStatus.APPROVED:
                chain = (
                    set_legal_name_from_provider_response.si(str(submission.pk))
                    | sync_bank_account_kyc_match.si(str(submission.pk))
                )
                chain.delay()
                triggered += 1
        self.message_user(
            request,
            f"🔄 Triggered legal_name population task for {triggered} submission(s). "
            "Check Celery logs for results.",
            level=messages.INFO,
        )
    action_trigger_legal_name_task.short_description = "🔄 Re-run legal_name population task"  # type: ignore[attr-defined]


@admin.register(KycDocument)
class KycDocumentAdmin(admin.ModelAdmin):
    """Standalone document audit surface."""

    list_display = ("submission", "document_type", "provider_verified", "created_at")
    list_filter = ("document_type", "provider_verified", "created_at")
    search_fields = ("submission__user__email", "public_id")
    readonly_fields = ("created_at", "updated_at")
