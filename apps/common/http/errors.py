from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class ProviderHTTPError(Exception):
    provider: str
    action: str
    message: str
    status_code: int | None = None
    response_payload: dict[str, Any] = field(default_factory=dict)
    reference: str = ""

    def __str__(self) -> str:
        status = f" status={self.status_code}" if self.status_code else ""
        ref = f" reference={self.reference}" if self.reference else ""
        return f"{self.provider}.{self.action}{status}{ref}: {self.message}"


class ProviderTimeoutError(ProviderHTTPError):
    pass


class ProviderConnectionError(ProviderHTTPError):
    pass


class ProviderHTTPStatusError(ProviderHTTPError):
    pass
