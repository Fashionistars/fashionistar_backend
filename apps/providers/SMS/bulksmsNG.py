# apps/providers/SMS/bulksmsNG.py
"""
BulkSMS Nigeria SMS provider — cost-effective local Nigerian delivery.

Required Django settings:
    BULKSMS_NG_API_TOKEN  = env("BULKSMS_NG_API_TOKEN")
    BULKSMS_NG_SENDER_ID  = env("BULKSMS_NG_SENDER_ID", default="Fashionistar")

Docs: https://www.bulksmsnigeria.com/sms-api-documentation
BulkSMS NG docs: https://www.bulksmsnigeria.com/api-documentation
"""

from __future__ import annotations

import asyncio
import logging

from django.conf import settings

from apps.common.http import ProviderSyncHTTPClient, RetryPolicy

logger = logging.getLogger("application")

_BULKSMS_BASE_URL = "https://www.bulksmsnigeria.com"


class BulksmsNGSMSProvider:
    """
    SMS provider using BulkSMS Nigeria API, wired through ProviderSyncHTTPClient.
    """

    def __init__(self, config=None) -> None:
        self.api_token: str = getattr(config, "api_key", "") or getattr(settings, "BULKSMS_NG_API_TOKEN", "")
        self.sender_id: str = getattr(config, "sender_id", "") or getattr(settings, "BULKSMS_NG_SENDER_ID", "Fashionistar")
        extra = getattr(config, "extra_config", {}) or {}
        self.dnd: int = int(extra.get("dnd", 1))
        self._http = ProviderSyncHTTPClient(
            provider="bulksmsng",
            base_url=_BULKSMS_BASE_URL,
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=1.0),
        )

    def send(self, to: str, body: str) -> str:
        resp = self._http.request(
            "POST",
            "/api/v1/sms/create",
            action="send_sms",
            reference=to,
            json={
                "api_token": self.api_token,
                "to": to,
                "from": self.sender_id,
                "body": body,
                "dnd": self.dnd,
            },
        )
        data = resp.data
        if data.get("status") == "success":
            message_id = str(data.get("data", {}).get("id", ""))
            logger.info("SMS sent via BulkSMS NG to %s, ID: %s", to, message_id)
            return message_id
        raise RuntimeError(
            f"BulkSMS NG API error: {data.get('message', 'Unknown error')}"
        )

    async def asend(self, to: str, body: str) -> str:
        return await asyncio.to_thread(self.send, to, body)
