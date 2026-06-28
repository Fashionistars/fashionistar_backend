# apps/kyc/apis/sync/kyc_views.py
"""
KYC Domain — DRF Synchronous Views.

Mounted at: /api/v1/kyc/

Architecture:
  ─ All MUTATION endpoints are here (DRF sync surface).
  ─ Read-only endpoints are on the Ninja async surface (/api/v1/ninja/kyc/).
  ─ All mutations delegate to KycService (sync, transaction.atomic).
  ─ Serializers validate input; services own business logic.

Endpoints:
  GET  /api/v1/kyc/status/               — KYC status with documents (sync)
  POST /api/v1/kyc/submit/               — Initiate / reopen KYC submission
  POST /api/v1/kyc/documents/upload/     — Record a Cloudinary document upload
  POST /api/v1/kyc/admin/<id>/approve/   — Admin: approve a submission
  POST /api/v1/kyc/admin/<id>/reject/    — Admin: reject a submission
"""
import logging

from django.core.exceptions import ObjectDoesNotExist
from rest_framework import generics, permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.kyc.selectors import get_kyc_submission_for_user
from apps.kyc.serializers import (
    KycSubmissionSerializer,
    KycSubmitSerializer,
    KycDocumentSerializer,
    KycDocumentUploadSerializer,
)
from apps.kyc.services import KycService

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# STATUS (sync read — available for DRF clients)
# ─────────────────────────────────────────────────────────────────────────────


class KycStatusView(APIView):
    """
    GET /api/v1/kyc/status/

    Returns the authenticated user's KYC submission with all documents.
    Delegates to get_kyc_submission_for_user selector (prefetch_related).
    Returns 200 with status='not_started' if no submission exists.
    """
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        submission = get_kyc_submission_for_user(request.user)
        if submission is None:
            return Response(
                {
                    "status": "success",
                    "data": {
                        "status": "not_started",
                        "is_approved": False,
                        "is_pending": False,
                        "is_rejected": False,
                        "can_resubmit": False,
                        "documents": [],
                    },
                }
            )
        serializer = KycSubmissionSerializer(submission)
        return Response({"status": "success", "data": serializer.data})


# ─────────────────────────────────────────────────────────────────────────────
# SUBMIT (initiate KYC)
# ─────────────────────────────────────────────────────────────────────────────


class KycSubmitView(APIView):
    """
    POST /api/v1/kyc/submit/

    Initiate or reopen a KYC submission.

    - If no submission exists → creates PENDING submission.
    - If submission is REJECTED / RESUBMIT → resets to PENDING.
    - If submission is APPROVED / PENDING / IN_REVIEW → returns current state (idempotent).

    Body (optional):
        { "nin": "12345678901", "bvn": "12345678901" }
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = KycSubmitSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            submission = KycService.initiate_submission(
                user=request.user,
                nin=vd.get("nin", ""),
                bvn=vd.get("bvn", ""),
            )
        except Exception:
            logger.exception(
                "KycSubmitView.post: error for user=%s", request.user.pk
            )
            return Response(
                {"detail": "Failed to initiate KYC submission. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        out = KycSubmissionSerializer(submission)
        status_code = (
            status.HTTP_201_CREATED
            if submission.status == "pending" and not submission.reviewed_at
            else status.HTTP_200_OK
        )
        return Response(
            {"status": "success", "message": "KYC submission initiated.", "data": out.data},
            status=status_code,
        )


# ─────────────────────────────────────────────────────────────────────────────
# DOCUMENT UPLOAD RECORDING
# ─────────────────────────────────────────────────────────────────────────────


class KycDocumentUploadView(APIView):
    """
    POST /api/v1/kyc/documents/upload/

    Record a KYC document Cloudinary upload against the user's active submission.

    Documents must be uploaded client-side to Cloudinary first using a
    presigned token from GET /api/v1/common/cloudinary/presign/?preset=kyc_docs.
    This endpoint records the resulting Cloudinary asset reference.

    Body:
        {
            "document_type": "nin_card",
            "document_number": "12345678901",
            "secure_url": "https://res.cloudinary.com/.../...",
            "public_id": "fashionistar/kyc/<user_id>/..."
        }

    Idempotent per (submission, document_type): re-uploading the same
    document type updates the existing record.
    """
    permission_classes = [permissions.IsAuthenticated]

    def post(self, request):
        serializer = KycDocumentUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        vd = serializer.validated_data

        try:
            doc = KycService.record_document(
                user=request.user,
                document_type=vd["document_type"],
                secure_url=vd["secure_url"],
                public_id=vd["public_id"],
                document_number=vd.get("document_number", ""),
            )
        except ValueError as exc:
            return Response(
                {"detail": str(exc)},
                status=status.HTTP_422_UNPROCESSABLE_ENTITY,
            )
        except Exception:
            logger.exception(
                "KycDocumentUploadView.post: error for user=%s", request.user.pk
            )
            return Response(
                {"detail": "Failed to record document. Please try again."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        out = KycDocumentSerializer(doc)
        return Response(
            {"status": "success", "message": "Document recorded.", "data": out.data},
            status=status.HTTP_201_CREATED,
        )


# ─────────────────────────────────────────────────────────────────────────────
# ADMIN REVIEW ACTIONS (staff only)
# ─────────────────────────────────────────────────────────────────────────────


class KycApproveView(APIView):
    """
    POST /api/v1/kyc/admin/<submission_id>/approve/

    Staff action: approve a KYC submission.

    Side effects:
      - Sets submission.status = APPROVED.
      - Sets VendorSetupState.id_verified = True (if user is a vendor).
      - Sends approval notification to the user.

    Body (optional):
        { "provider_reference": "smile_identity_job_123" }
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, submission_id):
        provider_reference = request.data.get("provider_reference", "")
        try:
            submission = KycService.approve_submission(
                submission_id=submission_id,
                admin_user=request.user,
                provider_reference=provider_reference,
            )
        except ObjectDoesNotExist:
            return Response(
                {"detail": "KYC submission not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except Exception:
            logger.exception(
                "KycApproveView.post: error for submission=%s", submission_id
            )
            return Response(
                {"detail": "Approval failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        out = KycSubmissionSerializer(submission)
        return Response(
            {"status": "success", "message": "KYC submission approved.", "data": out.data}
        )


class KycRejectView(APIView):
    """
    POST /api/v1/kyc/admin/<submission_id>/reject/

    Staff action: reject a KYC submission with review notes.

    Body:
        {
            "review_notes": "NIN document is blurry. Please resubmit a clearer photo.",
            "allow_resubmit": true
        }
    """
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def post(self, request, submission_id):
        review_notes = request.data.get("review_notes", "")
        allow_resubmit = request.data.get("allow_resubmit", True)

        if not review_notes.strip():
            return Response(
                {"detail": "review_notes is required for rejection."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        try:
            submission = KycService.reject_submission(
                submission_id=submission_id,
                admin_user=request.user,
                review_notes=review_notes,
                allow_resubmit=allow_resubmit,
            )
        except ObjectDoesNotExist:
            return Response(
                {"detail": "KYC submission not found."},
                status=status.HTTP_404_NOT_FOUND,
            )
        except PermissionError as exc:
            return Response({"detail": str(exc)}, status=status.HTTP_403_FORBIDDEN)
        except Exception:
            logger.exception(
                "KycRejectView.post: error for submission=%s", submission_id
            )
            return Response(
                {"detail": "Rejection failed."},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        out = KycSubmissionSerializer(submission)
        return Response(
            {"status": "success", "message": "KYC submission rejected.", "data": out.data}
        )


class KycAdminSubmissionListView(generics.ListAPIView):
    """
    GET /api/v1/kyc/admin/submissions/

    Staff-only endpoint to list all KYC submissions with users and documents.
    """
    serializer_class = KycSubmissionSerializer
    permission_classes = [permissions.IsAuthenticated, permissions.IsAdminUser]

    def get_queryset(self):
        from apps.kyc.models.kyc_submission import KycSubmission
        return KycSubmission.objects.select_related("user").prefetch_related("documents").order_by("-updated_at")

    def list(self, request, *args, **kwargs):
        queryset = self.filter_queryset(self.get_queryset())
        page = self.paginate_queryset(queryset)
        if page is not None:
            serializer = self.get_serializer(page, many=True)
            return self.get_paginated_response(serializer.data)

        serializer = self.get_serializer(queryset, many=True)
        return Response({
            "status": "success",
            "message": "KYC submissions retrieved successfully.",
            "data": serializer.data
        })

