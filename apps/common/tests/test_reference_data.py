from django.core.exceptions import ValidationError
from rest_framework.test import APIClient

from apps.common.reference_data.banks import get_banks
from apps.common.reference_data.locations import get_cities, get_lgas, get_states
from apps.common.reference_data.validators import (
    validate_bank_code,
    validate_city_or_custom_city,
    validate_country_code,
    validate_lga_code,
    validate_state_code,
    validate_street_address,
)


def test_reference_data_loads_full_nigeria_depth():
    states = get_states("NG")
    lgas = get_lgas("NG", "LAGOS")
    cities = get_cities("NG", state_ref="LAGOS", lga_ref="IKEJA")

    assert len(states) == 37
    assert len(lgas) >= 20
    assert cities
    assert any(city["name"].lower() == "wasimi/opebi/allen" for city in cities)


def test_reference_validators_accept_normalized_address_and_bank():
    assert validate_country_code("ng") == "NG"
    assert validate_state_code("NG", "Lagos") == "Lagos"
    assert validate_lga_code("NG", "Lagos", "Ikeja") == "Ikeja"
    assert validate_city_or_custom_city("NG", "Lagos", "Ikeja", city_code="Wasimi/Opebi/Allen") == {
        "city_code": "Wasimi/Opebi/Allen",
        "custom_city": None,
    }
    assert validate_city_or_custom_city("NG", "Lagos", "Ikeja", custom_city="Fashion District") == {
        "city_code": None,
        "custom_city": "Fashion District",
    }
    assert validate_street_address("12 Okigwe Street") == "12 Okigwe Street"
    assert validate_bank_code("044", "NG") == "044"


def test_reference_validators_reject_untrusted_values():
    for callback in (
        lambda: validate_country_code("XX"),
        lambda: validate_state_code("NG", "Atlantis"),
        lambda: validate_lga_code("NG", "Lagos", "Unknown LGA"),
        lambda: validate_city_or_custom_city("NG", "Lagos", "Ikeja", custom_city="<script>"),
        lambda: validate_street_address("x"),
        lambda: validate_bank_code("000-NOT-A-BANK", "NG"),
    ):
        try:
            callback()
        except ValidationError:
            continue
        raise AssertionError("Expected reference validator to reject invalid input")


def test_reference_data_endpoints_return_static_payloads():
    client = APIClient()

    countries = client.get("/api/v1/common/reference/countries/")
    states = client.get("/api/v1/common/reference/countries/NG/states/")
    lgas = client.get("/api/v1/common/reference/countries/NG/states/LAGOS/lgas/")
    cities = client.get(
        "/api/v1/common/reference/countries/NG/cities/",
        {"state": "LAGOS", "lga": "IKEJA"},
    )
    banks = client.get("/api/v1/common/reference/banks/", {"country": "NG"})

    assert countries.status_code == 200
    assert states.status_code == 200
    assert lgas.status_code == 200
    assert cities.status_code == 200
    assert banks.status_code == 200
    assert len(states.json()["data"]) == 37
    assert any(bank["code"] == "044" for bank in banks.json()["data"])
    assert len(get_banks("NG")) >= 100
