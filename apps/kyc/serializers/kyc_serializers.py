# apps/kyc/serializers/kyc_serializers.py
"""
DRF Serializers for the KYC domain.

Architecture:
  - KycSubmissionSerializer: read-only, full submission details.
  - KycSubmitSerializer: write — for initiating a submission.
  - KycDocumentSerializer: read-only, single document view.
  - KycDocumentUploadSerializer: write — for uploading a KYC document.

Security:
  - Document file content is handled via Cloudinary presigned upload.
    This serializer only accepts the Cloudinary secure_url + public_id.
  - Owner is always injected from request.user — never from the payload.
"""
from rest_framework import serializers

from apps.kyc.models.kyc_submission import KycSubmission, KycStatus
from apps.kyc.models.kyc_document import KycDocument, KycDocumentType


class KycDocumentSerializer(serializers.ModelSerializer):
    """Read serializer for a single KYC document."""

    class Meta:
        model = KycDocument
        fields = [
            "id",
            "document_type",
            "document_number",
            "secure_url",
            "public_id",
            "provider_verified",
            "provider_response",
            "uploaded_at",
        ]
        read_only_fields = fields


class KycSubmissionSerializer(serializers.ModelSerializer):
    """
    Read serializer for a KycSubmission including nested documents.
    Used for GET /api/v1/kyc/status/ and detail views.
    """
    documents = KycDocumentSerializer(many=True, read_only=True)
    is_approved = serializers.BooleanField(read_only=True)
    is_pending = serializers.BooleanField(read_only=True)
    is_rejected = serializers.BooleanField(read_only=True)
    can_resubmit = serializers.BooleanField(read_only=True)
    user = serializers.SerializerMethodField(read_only=True)

    class Meta:
        model = KycSubmission
        fields = [
            "id",
            "user",
            "status",
            "is_approved",
            "is_pending",
            "is_rejected",
            "can_resubmit",
            "review_notes",
            "provider_reference",
            "submitted_at",
            "reviewed_at",
            "documents",
            "created_at",
            "updated_at",
        ]
        read_only_fields = fields

    def get_user(self, obj):
        user = obj.user
        avatar_url = None
        if user.avatar:
            avatar_url = user.avatar.url if hasattr(user.avatar, "url") else str(user.avatar)
        return {
            "id": str(user.id),
            "email": user.email,
            "phone": str(user.phone) if user.phone else None,
            "first_name": user.first_name,
            "last_name": user.last_name,
            "role": user.role,
            "avatar": avatar_url,
        }



# ─────────────────────────────────────────────────────────────────────────────
# WRITE SERIALIZERS
# ─────────────────────────────────────────────────────────────────────────────


class KycSubmitSerializer(serializers.Serializer):
    """
    Write serializer for initiating a KYC submission.

    The user declares their intent to verify. This creates (or re-opens)
    a KycSubmission record. Document uploads happen separately.
    """
    # Optional initial NIN / BVN supplied at submission start
    nin = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        help_text="Nigerian National Identification Number (11 digits).",
    )
    bvn = serializers.CharField(
        max_length=20,
        required=False,
        allow_blank=True,
        help_text="Bank Verification Number (11 digits).",
    )


class KycDocumentUploadSerializer(serializers.Serializer):
    """
    Write serializer for recording a KYC document upload.

    Documents are uploaded client-side to Cloudinary using a presigned token
    (GET /api/v1/common/cloudinary/presign/?preset=kyc_docs).
    This endpoint records the Cloudinary asset reference after upload.
    """
    document_type = serializers.ChoiceField(
        choices=KycDocumentType.choices,
        help_text=(
            "Type of identity document: nin_card, bvn_slip, passport, "
            "drivers_license, cac_certificate, utility_bill."
        ),
    )
    document_number = serializers.CharField(
        max_length=50,
        required=False,
        allow_blank=True,
        help_text="The document number / ID (e.g., NIN number, passport number).",
    )
    secure_url = serializers.URLField(
        help_text="Cloudinary secure_url returned after client-side upload.",
    )
    public_id = serializers.CharField(
        max_length=300,
        help_text="Cloudinary public_id returned after client-side upload.",
    )
