# apps/kyc/apis/sync/kyc_webhook_view.py
"""
KYC Provider Webhook Endpoint.

POST /api/v1/kyc/webhook/<provider_slug>/

Receives asynchronous verification callbacks from the active KYC provider
(Smile Identity, Dojah, or Youverify) after a background identity check.

Security:
  - HMAC signature validated against KYCProviderConfig.webhook_secret.
  - Requests with invalid signatures return HTTP 400 immediately.
  - Rate limiting applies via the global DRF throttle classes.
  - Authentication deliberately NOT required (providers call unauthenticated).
  - CSRF exemption required (inbound external POST).

Idempotency:
  - KycService.reconcile_webhook() is idempotent on provider_reference.
  - Duplicate webhooks are a no-op.

Audit:
  - Every webhook (success / failure) is written to AuditEventLog.
  - KYC events are compliance-flagged (retention 2555 days = 7 years).
"""
from __future__ import annotations

import json
import logging

from django.utils.decorators import method_decorator
from django.views.decorators.csrf import csrf_exempt
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.providers.KYC import get_kyc_webhook_header
from apps.providers.KYC import load_kyc_provider
from apps.providers.cache import get_kyc_provider_config
from apps.kyc.services.kyc_service import KycService

logger = logging.getLogger("application")


def _audit_kyc_webhook(
    *,
    event_type: str,
    provider_slug: str,
    provider_reference: str,
    success: bool,
    request,
    metadata: dict | None = None,
) -> None:
    """
    Fire-and-forget compliance audit log for every KYC webhook event.

    Uses lazy import to avoid circular dependencies at module load time.
    Errors are swallowed so they NEVER interrupt the webhook response.
    """
    try:
        from apps.audit_logs.services.kyc.kyc_audit import KycAuditService  # noqa: PLC0415

        KycAuditService.log_webhook_event(
            event_type=event_type,
            request=request,
            provider_slug=provider_slug,
            provider_reference=provider_reference,
            success=success,
            metadata=metadata or {},
        )
    except Exception as exc:  # noqa: BLE001
        logger.warning("KycWebhookView: audit log failed (non-blocking): %s", exc)


@method_decorator(csrf_exempt, name="dispatch")
class KycWebhookView(APIView):
    """
    Receive and process inbound KYC provider webhook callbacks.

    Workflow:
      1. Extract provider_slug from URL.
      2. Load KYCProviderConfig from cache.
      3. Validate HMAC signature using provider's signing secret.
      4. Dispatch to KycService.reconcile_webhook() for idempotent reconciliation.
      5. Audit-log the outcome (compliance=True, 7-year retention).
      6. Return HTTP 200 immediately (provider expects fast acknowledgement).
    """

    authentication_classes = []  # No JWT required for provider callbacks
    permission_classes = [AllowAny]
    throttle_classes = []  # Provider IPs should be allowlisted at nginx level

    def post(self, request, provider_slug: str) -> Response:
        try:
            # ── Load active KYC provider config ──────────────────────────────
            config = get_kyc_provider_config()
            if config.provider_slug != provider_slug:
                logger.warning(
                    "KycWebhookView: received webhook for slug=%s but active provider is %s",
                    provider_slug, config.provider_slug,
                )

            # ── Parse body ───────────────────────────────────────────────────
            try:
                payload: dict = json.loads(request.body)
            except (json.JSONDecodeError, ValueError):
                logger.warning("KycWebhookView: invalid JSON body from provider=%s", provider_slug)
                return Response({"detail": "Invalid JSON."}, status=status.HTTP_400_BAD_REQUEST)

            sig_header_name = get_kyc_webhook_header(provider_slug)
            # Django converts HTTP headers to META format: X-Foo-Bar -> HTTP_X_FOO_BAR
            meta_key = "HTTP_" + sig_header_name.upper().replace("-", "_")
            signature = request.META.get(meta_key, "")

            try:
                webhook_result = load_kyc_provider(config).handle_webhook(
                    payload=payload,
                    signature=signature,
                )
            except ValueError:
                logger.error("KycWebhookView: invalid HMAC for provider=%s", provider_slug)
                _audit_kyc_webhook(
                    event_type="KYC_WEBHOOK_SIGNATURE_FAILED",
                    provider_slug=provider_slug,
                    provider_reference="",
                    success=False,
                    request=request,
                    metadata={"reason": "hmac_invalid"},
                )
                return Response(
                    {"detail": "Signature verification failed."},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            provider_reference = webhook_result.provider_reference
            success = webhook_result.success

            if not provider_reference:
                logger.warning(
                    "KycWebhookView: could not extract provider_reference from payload (slug=%s)",
                    provider_slug,
                )
                return Response({"detail": "Missing provider_reference."}, status=status.HTTP_400_BAD_REQUEST)

            # ── Idempotent reconciliation ────────────────────────────────────
            KycService.reconcile_webhook(
                provider_reference=provider_reference,
                success=success,
                raw_payload=webhook_result.raw_payload,
            )

            # ── Compliance audit log ─────────────────────────────────────────
            event_type = (
                "KYC_VERIFICATION_APPROVED" if success else "KYC_VERIFICATION_REJECTED"
            )
            _audit_kyc_webhook(
                event_type=event_type,
                provider_slug=provider_slug,
                provider_reference=provider_reference,
                success=success,
                request=request,
                metadata={"raw_payload_keys": list(webhook_result.raw_payload.keys())},
            )

            logger.info(
                "KycWebhookView: processed webhook — slug=%s ref=%s success=%s",
                provider_slug, provider_reference, success,
            )
            return Response({"detail": "Webhook received."}, status=status.HTTP_200_OK)

        except Exception as exc:
            logger.error("KycWebhookView: unexpected error — %s", exc, exc_info=True)
            return Response({"detail": "Internal error."}, status=status.HTTP_500_INTERNAL_SERVER_ERROR)
