from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RetryPolicy:
    max_attempts: int = 1
    backoff_seconds: float = 0.25
    retry_methods: set[str] = field(
        default_factory=lambda: {"GET", "HEAD", "OPTIONS"}
    )
    retry_status_codes: set[int] = field(
        default_factory=lambda: {408, 429, 500, 502, 503, 504}
    )

    def should_retry(
        self,
        *,
        method: str,
        attempt: int,
        status_code: int | None = None,
        idempotency_key: str = "",
    ) -> bool:
        if attempt >= self.max_attempts:
            return False
        method = method.upper()
        if method not in self.retry_methods and not idempotency_key:
            return False
        if status_code is None:
            return True
        return status_code in self.retry_status_codes
