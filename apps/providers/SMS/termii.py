# apps/providers/SMS/termii.py
"""
Termii SMS provider — Nigeria-native focused, excellent local delivery. carrier with OTP and transactional routing.

Required Django settings:
    TERMII_API_KEY    = env("TERMII_API_KEY")
    TERMII_SENDER_ID  = env("TERMII_SENDER_ID", default="Fashionistar")

Termii docs: https://developers.termii.com/messaging
Docs: https://developers.termii.com/sending-a-message

"""

from __future__ import annotations

import asyncio
import logging

from django.conf import settings

from apps.common.http import ProviderSyncHTTPClient, RetryPolicy

logger = logging.getLogger("application")

_TERMII_BASE_URL = "https://api.ng.termii.com"


class TermiiSMSProvider:
    """
    SMS provider using Termii API, wired through ProviderSyncHTTPClient
    (idempotency-key, structured logs, retry, circuit-safe exceptions).
    """

    def __init__(self, config=None) -> None:
        self.api_key: str = getattr(config, "api_key", "") or getattr(settings, "TERMII_API_KEY", "")
        self.sender_id: str = getattr(config, "sender_id", "") or getattr(settings, "TERMII_SENDER_ID", "Fashionistar")
        extra = getattr(config, "extra_config", {}) or {}
        self.channel: str = extra.get("channel", "generic")
        self._http = ProviderSyncHTTPClient(
            provider="termii",
            base_url=_TERMII_BASE_URL,
            retry_policy=RetryPolicy(max_attempts=3, backoff_seconds=1.0),
        )

    def send(self, to: str, body: str) -> str:
        resp = self._http.request(
            "POST",
            "/api/sms/send",
            action="send_sms",
            reference=to,
            json={
                "to": to,
                "from": self.sender_id,
                "sms": body,
                "type": "plain",
                "channel": self.channel,
                "api_key": self.api_key,
            },
        )
        data = resp.data
        if data.get("code") == "20" or data.get("status") == "success":
            message_id = str(data.get("message_id", ""))
            logger.info("SMS sent via Termii to %s, ID: %s", to, message_id)
            return message_id
        raise RuntimeError(f"Termii API error: {data.get('message', 'Unknown error')}")

    async def asend(self, to: str, body: str) -> str:
        return await asyncio.to_thread(self.send, to, body)
