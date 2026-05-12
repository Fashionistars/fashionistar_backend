from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from apps.common.http.errors import (
    ProviderConnectionError,
    ProviderHTTPError,
    ProviderHTTPStatusError,
    ProviderTimeoutError,
)
from apps.common.http.retry import RetryPolicy

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = httpx.Timeout(connect=5.0, read=30.0, write=30.0, pool=5.0)
DEFAULT_LIMITS = httpx.Limits(max_connections=100, max_keepalive_connections=20)


@dataclass(slots=True)
class ProviderHTTPResponse:
    status_code: int
    data: dict[str, Any]
    text: str
    elapsed_ms: float
    headers: dict[str, str] = field(default_factory=dict)


def _json_or_empty(response: httpx.Response) -> dict[str, Any]:
    try:
        data = response.json()
    except ValueError:
        return {}
    return data if isinstance(data, dict) else {"data": data}


class ProviderSyncHTTPClient:
    def __init__(
        self,
        *,
        provider: str,
        base_url: str,
        timeout: httpx.Timeout = DEFAULT_TIMEOUT,
        limits: httpx.Limits = DEFAULT_LIMITS,
        retry_policy: RetryPolicy | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.provider = provider
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.limits = limits
        self.retry_policy = retry_policy or RetryPolicy()
        self.transport = transport

    def request(
        self,
        method: str,
        path: str,
        *,
        action: str,
        reference: str = "",
        idempotency_key: str = "",
        headers: dict[str, str] | None = None,
        **kwargs,
    ) -> ProviderHTTPResponse:
        method = method.upper()
        path = path if path.startswith("/") else f"/{path}"
        request_headers = dict(headers or {})
        if idempotency_key:
            request_headers.setdefault("Idempotency-Key", idempotency_key)

        attempt = 1
        while True:
            started = time.perf_counter()
            try:
                with httpx.Client(
                    base_url=self.base_url,
                    timeout=self.timeout,
                    limits=self.limits,
                    transport=self.transport,
                ) as client:
                    response = client.request(
                        method,
                        path,
                        headers=request_headers,
                        **kwargs,
                    )
                elapsed_ms = (time.perf_counter() - started) * 1000
                data = _json_or_empty(response)
                logger.info(
                    "provider_http",
                    extra={
                        "provider": self.provider,
                        "action": action,
                        "reference": reference,
                        "status_code": response.status_code,
                        "duration_ms": round(elapsed_ms, 2),
                        "attempt": attempt,
                    },
                )
                if response.is_error:
                    if self.retry_policy.should_retry(
                        method=method,
                        attempt=attempt,
                        status_code=response.status_code,
                        idempotency_key=idempotency_key,
                    ):
                        attempt += 1
                        time.sleep(self.retry_policy.backoff_seconds * attempt)
                        continue
                    raise ProviderHTTPStatusError(
                        provider=self.provider,
                        action=action,
                        message=data.get("message") or response.text,
                        status_code=response.status_code,
                        response_payload=data,
                        reference=reference,
                    )
                return ProviderHTTPResponse(
                    status_code=response.status_code,
                    data=data,
                    text=response.text,
                    elapsed_ms=elapsed_ms,
                    headers=dict(response.headers),
                )
            except httpx.TimeoutException as exc:
                if self.retry_policy.should_retry(
                    method=method,
                    attempt=attempt,
                    idempotency_key=idempotency_key,
                ):
                    attempt += 1
                    time.sleep(self.retry_policy.backoff_seconds * attempt)
                    continue
                raise ProviderTimeoutError(
                    provider=self.provider,
                    action=action,
                    message=str(exc) or "Provider request timed out.",
                    reference=reference,
                ) from exc
            except httpx.RequestError as exc:
                if self.retry_policy.should_retry(
                    method=method,
                    attempt=attempt,
                    idempotency_key=idempotency_key,
                ):
                    attempt += 1
                    time.sleep(self.retry_policy.backoff_seconds * attempt)
                    continue
                raise ProviderConnectionError(
                    provider=self.provider,
                    action=action,
                    message=str(exc) or "Provider request failed.",
                    reference=reference,
                ) from exc
            except ProviderHTTPError:
                raise
