# apps/kyc/apps.py
"""
KYC Domain AppConfig.

Connects the post_save signal to auto-populate legal_name on KYC approval.
"""
from django.apps import AppConfig


class KycConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.kyc"
    verbose_name = "KYC Compliance"
    label = "kyc"

    def ready(self) -> None:
        """Connect post_save signal to dispatch legal_name population task."""
        from django.db.models.signals import post_save
        from django.dispatch import receiver

        def _on_kyc_submission_saved(sender, instance, created, **kwargs):
            """
            When a KycSubmission transitions to APPROVED, dispatch a Celery
            task to extract the legal name from the provider verification
            response. Also chains a second task to retroactively update
            kyc_name_matched on existing VendorBankAccount records.

            Uses transaction.on_commit to ensure tasks only fire after the
            database write is fully committed.
            """
            from apps.kyc.models.kyc_submission import KycStatus
            from django.db import transaction

            if instance.status == KycStatus.APPROVED and not (instance.legal_name and instance.legal_name.strip()):
                submission_id = str(instance.pk)

                def _dispatch():
                    from apps.kyc.tasks import (
                        set_legal_name_from_provider_response,
                        sync_bank_account_kyc_match,
                    )
                    # Task chain: populate legal_name → then refresh bank account matches
                    chain = (
                        set_legal_name_from_provider_response.si(submission_id)
                        | sync_bank_account_kyc_match.si(submission_id)
                    )
                    chain.delay()

                transaction.on_commit(_dispatch)

        from apps.kyc.models import KycSubmission
        post_save.connect(_on_kyc_submission_saved, sender=KycSubmission, weak=False)
