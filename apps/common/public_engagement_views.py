"""
Public unauthenticated engagement endpoints.

Canonical write surface:
  - POST /api/v1/public/contact/
  - POST /api/v1/public/newsletter/
  - POST /api/v1/public/waitlist/

Reads stay on the async Ninja surface; these writes stay sync DRF by design.
"""

from __future__ import annotations

from django.conf import settings
from django.db import transaction
from rest_framework import generics, status
from rest_framework.permissions import AllowAny

from apps.common.responses import error_response, success_response
from apps.common.serializers import (
    ContactSubmissionSerializer,
    NewsletterSignupSerializer,
    WaitlistSignupSerializer,
)
from apps.common.tasks.engagement import send_public_engagement_email
from apps.global_platform_settings.cache import get_platform_settings


def _support_inbox() -> str:
    cfg = get_platform_settings()
    return cfg.support_email or getattr(settings, "DEFAULT_FROM_EMAIL", "support@fashionistar.net")


def _schedule_notification(*, subject: str, message: str) -> None:
    recipient = _support_inbox()

    def _dispatch() -> None:
        send_public_engagement_email.apply_async(
            kwargs={
                "subject": subject,
                "recipients": [recipient],
                "message": message,
            }
        )

    transaction.on_commit(_dispatch)


class PublicNewsletterSignupView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = NewsletterSignupSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Please provide a valid email address.",
                code="validation_error",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = serializer.validated_data
        with transaction.atomic():
            _schedule_notification(
                subject="Public newsletter signup",
                message=(
                    "A new newsletter signup was captured.\n\n"
                    f"Email: {payload['email']}\n"
                    f"Source: {payload.get('source') or 'newsletter'}\n"
                ),
            )

        return success_response(
            data={
                "email": payload["email"],
                "source": payload.get("source") or "newsletter",
            },
            message="Newsletter signup received successfully.",
            status=status.HTTP_202_ACCEPTED,
        )


class PublicWaitlistSignupView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = WaitlistSignupSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Please provide a valid email address.",
                code="validation_error",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = serializer.validated_data
        with transaction.atomic():
            _schedule_notification(
                subject="Public waitlist signup",
                message=(
                    "A new waitlist signup was captured.\n\n"
                    f"Email: {payload['email']}\n"
                    f"Source: {payload.get('source') or 'waitlist'}\n"
                ),
            )

        return success_response(
            data={
                "email": payload["email"],
                "source": payload.get("source") or "waitlist",
            },
            message="Waitlist signup received successfully.",
            status=status.HTTP_202_ACCEPTED,
        )


class PublicContactSubmissionView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    serializer_class = ContactSubmissionSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Please review the highlighted fields and try again.",
                code="validation_error",
                errors=serializer.errors,
                status=status.HTTP_400_BAD_REQUEST,
            )

        payload = serializer.validated_data
        subject = payload.get("subject") or "General enquiry"
        with transaction.atomic():
            _schedule_notification(
                subject=f"Public contact submission: {subject}",
                message=(
                    "A new public contact form submission was received.\n\n"
                    f"Name: {payload['full_name']}\n"
                    f"Email: {payload['email']}\n"
                    f"Phone: {payload.get('phone') or '-'}\n"
                    f"Subject: {subject}\n"
                    f"Vendor: {payload.get('vendor') or '-'}\n"
                    f"Inquiry type: {payload.get('inquiry_type') or '-'}\n"
                    f"Page URL: {payload.get('page_url') or '-'}\n\n"
                    "Message:\n"
                    f"{payload['message']}\n"
                ),
            )

        return success_response(
            data={
                "email": payload["email"],
                "subject": subject,
            },
            message="Your message has been received. Our team will follow up soon.",
            status=status.HTTP_202_ACCEPTED,
        )
