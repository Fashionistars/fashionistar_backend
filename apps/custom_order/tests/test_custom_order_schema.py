from django.db import ProgrammingError

import pytest

from apps.custom_order.models import CustomOrder


@pytest.mark.django_db
def test_custom_order_legacy_state_only_columns_are_queryable():
    """
    Regression guard for the legacy apps.order -> apps.custom_order ownership split.

    The database table was originally created in order.0008 before the custom_order
    app claimed ownership through SeparateDatabaseAndState. The legacy table must
    still contain the later state-only fields that Django expects to query.
    """

    try:
        list(
            CustomOrder.objects.values_list(
                "currency",
                "approved_at",
                "completed_at",
            )[:1]
        )
    except ProgrammingError as exc:  # pragma: no cover - exercised on broken schema
        pytest.fail(f"custom_order legacy columns are missing from the database schema: {exc}")
