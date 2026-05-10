"""Tests for public Ninja reference-data endpoints."""

from __future__ import annotations

import pytest
from rest_framework.test import APIClient


@pytest.mark.django_db
def test_ninja_reference_countries_endpoint_is_public():
    """The async countries endpoint should be reachable without auth."""

    response = APIClient().get("/api/v1/ninja/common/reference/countries/")

    assert response.status_code == 200
    payload = response.json()
    assert isinstance(payload, list)
    assert any(country["code"] == "NG" for country in payload)


@pytest.mark.django_db
def test_ninja_reference_states_endpoint_validates_country_code():
    """Invalid country codes should be rejected with a 400 response."""

    response = APIClient().get("/api/v1/ninja/common/reference/countries/XX/states/")

    assert response.status_code == 400
