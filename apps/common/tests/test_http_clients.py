import asyncio

import pytest
import httpx

from apps.common.http import (
    ProviderAsyncHTTPClient,
    ProviderHTTPStatusError,
    ProviderSyncHTTPClient,
    ProviderTimeoutError,
)


def test_sync_provider_client_forwards_idempotency_key_and_parses_json():
    seen_headers = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers["idempotency"] = request.headers.get("Idempotency-Key")
        return httpx.Response(200, json={"status": True, "data": {"ok": True}})

    client = ProviderSyncHTTPClient(
        provider="test",
        base_url="https://provider.test",
        transport=httpx.MockTransport(handler),
    )

    response = client.request(
        "POST",
        "/payments",
        action="payment.create",
        idempotency_key="idem-001",
    )

    assert response.status_code == 200
    assert response.data["status"] is True
    assert seen_headers["idempotency"] == "idem-001"


def test_sync_provider_client_normalizes_failed_response():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(503, json={"message": "provider unavailable"})

    client = ProviderSyncHTTPClient(
        provider="test",
        base_url="https://provider.test",
        transport=httpx.MockTransport(handler),
    )

    with pytest.raises(ProviderHTTPStatusError) as exc:
        client.request("GET", "/banks", action="bank.list")

    assert exc.value.status_code == 503
    assert exc.value.response_payload["message"] == "provider unavailable"


def test_async_provider_client_normalizes_timeout():
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("provider timed out", request=request)

    async def run_case():
        client = ProviderAsyncHTTPClient(
            provider="test",
            base_url="https://provider.test",
            transport=httpx.MockTransport(handler),
        )

        with pytest.raises(ProviderTimeoutError):
            await client.request("GET", "/verify/ref", action="payment.verify")

    asyncio.run(run_case())
