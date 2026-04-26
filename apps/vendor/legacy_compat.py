"""Temporary guards for legacy commerce dependencies during domain migration."""

from __future__ import annotations

from django.apps import apps


class LegacyCommerceUnavailable(RuntimeError):
    """Raised when a legacy commerce model is not available in installed apps."""


def get_legacy_store_model(model_name: str):
    try:
        return apps.get_model("store", model_name)
    except LookupError as exc:
        raise LegacyCommerceUnavailable(
            "Commerce data is temporarily unavailable while product, cart, and "
            "order domains are being migrated into modern apps."
        ) from exc
