# apps/providers/SMS/kudi.py
"""
Kudi SMS provider — Reliable Nigerian and international carrier.

Required Django settings:
    KUDI_API_KEY      = env("KUDI_API_KEY")
    KUDI_SENDER_ID    = env("KUDI_SENDER_ID", default="fashionistar")

Docs: https://my.kudisms.net/api/sms
"""

from __future__ import annotations

import asyncio
import logging

from django.conf import settings

from apps.common.http import ProviderSyncHTTPClient, RetryPolicy

logger = logging.getLogger("application")

_KUDI_BASE_URL = "https://my.kudisms.net"


class KudiSMSProvider:
    """
    SMS provider using Kudi SMS API, wired through ProviderSyncHTTPClient
    (structured logs, retry, circuit-safe exceptions).
    """

    def __init__(self, config=None) -> None:
        self.api_key: str = getattr(config, "api_key", "") or getattr(settings, "KUDI_API_KEY", "")
        self.sender_id: str = getattr(config, "sender_id", "") or getattr(settings, "KUDI_SENDER_ID", "fashionistar")
        extra = getattr(config, "extra_config", {}) or {}
        self.gateway: str = str(extra.get("gateway", "2"))  # 2 = DND refund gateway default
        self._http = ProviderSyncHTTPClient(
            provider="kudisms",
            base_url=_KUDI_BASE_URL,
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=1.0),
        )

    def send(self, to: str, body: str) -> str:
        # Kudi expects number format with country code (e.g. 2348012345678)
        # Clean the "to" number if it starts with '+'
        phone = to.lstrip("+")
        
        resp = self._http.request(
            "POST",
            "/api/sms",
            action="send_sms",
            reference=to,
            json={
                "token": self.api_key,
                "senderID": self.sender_id,
                "recipients": phone,
                "message": body,
                "gateway": self.gateway,
            },
        )
        data = resp.data
        if data.get("status") == "success" or data.get("error_code") == "000":
            # Extract first message ID or fallback to success status
            msg_data = data.get("data", [])
            message_id = ""
            if isinstance(msg_data, list) and msg_data:
                message_id = str(msg_data[0])
            else:
                message_id = "kudi_ok"
            
            logger.info("SMS sent via Kudi SMS to %s, ID: %s", to, message_id)
            return message_id
            
        raise RuntimeError(
            f"Kudi SMS API error: {data.get('msg', 'Unknown error')} (code: {data.get('error_code')})"
        )

    async def asend(self, to: str, body: str) -> str:
        return await asyncio.to_thread(self.send, to, body)