"""Focused regression tests for provider-backed KYC wiring."""

from __future__ import annotations

import pytest

from apps.kyc.models.kyc_document import KycDocument
from apps.kyc.models.kyc_submission import KycStatus, KycSubmission
from apps.kyc.services.kyc_service import KycService
from apps.providers.KYC import DojahProvider, SmileIdentityProvider, YouverifyProvider, load_kyc_provider
from apps.providers.models import KYCProviderConfig


@pytest.mark.parametrize(
    ("slug", "expected_class"),
    [
        ("dojah", DojahProvider),
        ("smileid", SmileIdentityProvider),
        ("youverify", YouverifyProvider),
    ],
)
def test_load_kyc_provider_resolves_configured_driver(slug, expected_class):
    config = KYCProviderConfig(provider_slug=slug, sandbox_mode=True)

    provider = load_kyc_provider(config)

    assert isinstance(provider, expected_class)


@pytest.mark.django_db
def test_kyc_webhook_reconcile_auto_approves_without_staff_user(django_user_model):
    user = django_user_model.objects.create_user(
        email="kyc-webhook-client@fashionistar.test",
        password="StrongPass123!",
        role="client",
    )
    submission = KycSubmission.objects.create(user=user, status=KycStatus.PENDING)
    KycDocument.objects.create(
        submission=submission,
        document_type="bvn_slip",
        secure_url="https://res.cloudinary.com/fashionistar/kyc/bvn.png",
        public_id="fashionistar/kyc/bvn",
        provider_response={"provider_reference": "provider-ref-123"},
    )

    KycService.reconcile_webhook(
        provider_reference="provider-ref-123",
        success=True,
        raw_payload={"event": "verification.complete"},
    )

    submission.refresh_from_db()
    assert submission.status == KycStatus.APPROVED
    assert submission.provider_reference == "provider-ref-123"

    doc = submission.documents.get(document_type="bvn_slip")
    assert doc.provider_verified is True
    assert doc.provider_response["webhook_reconciled"] is True
