# apps/global_platform_settings/views.py
"""
Public Platform Settings API — DRF View.

URL: GET /api/v1/platform/settings/public/

Exposes a curated, non-sensitive subset of PlatformSettings to authenticated
frontend clients. Used by the vendor payout flow to dynamically load
min/max withdrawal limits without hardcoding them in the frontend.

No authentication required — these are public business configuration values.
Cached via Redis via get_platform_settings() (60s TTL).
"""
from __future__ import annotations

from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.global_platform_settings.cache import get_platform_settings


class PublicPlatformSettingsView(APIView):
    """
    GET /api/v1/platform/settings/public/

    Returns public-safe platform configuration values for frontend use.
    Does NOT require authentication — these are public limits and branding.
    Response is backed by Redis (60s TTL) so it is cheap to call on every
    payout modal open.

    Response schema:
        {
            "platform_name": "Fashionistar",
            "min_withdrawal_ngn": "1000.00",
            "max_withdrawal_ngn": "2000000.00",
            "max_daily_withdrawal_ngn": "5000000.00",
            "min_wallet_topup_ngn": "500.00",
            "max_wallet_topup_ngn": "5000000.00",
            "support_email": "support@fashionistar.net",
            "support_phone": "+234 913 7654 300",
            "terms_url": "https://fashionistar.net/terms",
            "privacy_url": "https://fashionistar.net/privacy"
        }
    """
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]

    def get(self, request, *args, **kwargs):
        cfg = get_platform_settings()
        return Response({
            "platform_name":           cfg.platform_name,
            "min_withdrawal_ngn":      str(cfg.min_withdrawal_ngn),
            "max_withdrawal_ngn":      str(cfg.max_withdrawal_ngn),
            "max_daily_withdrawal_ngn": str(cfg.max_daily_withdrawal_ngn),
            "min_wallet_topup_ngn":    str(cfg.min_wallet_topup_ngn),
            "max_wallet_topup_ngn":    str(cfg.max_wallet_topup_ngn),
            "support_email":           cfg.support_email,
            "support_phone":           cfg.support_phone,
            "terms_url":               cfg.terms_url,
            "privacy_url":             cfg.privacy_url,
        })
