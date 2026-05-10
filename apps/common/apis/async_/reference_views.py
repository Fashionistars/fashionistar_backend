"""Async Django-Ninja router for public reference data reads."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from ninja import Query, Router
from ninja.errors import HttpError

from apps.common.reference_data.banks import get_banks
from apps.common.reference_data.countries import get_countries
from apps.common.reference_data.locations import get_cities, get_lgas, get_states
from apps.common.reference_data.validators import (
    validate_country_code,
    validate_lga_code,
    validate_state_code,
)
from apps.common.schemas.reference_data_schemas import (
    ReferenceBankOut,
    ReferenceCityOut,
    ReferenceCountryOut,
    ReferenceLgaOut,
    ReferenceStateOut,
)

router = Router(tags=["Common - Async Reference Data"], auth=None)


def _as_http_error(exc: DjangoValidationError) -> HttpError:
    """Translate Django validation errors into Ninja HTTP 400 responses."""

    message = exc.messages[0] if getattr(exc, "messages", None) else str(exc)
    return HttpError(400, message)


@router.get("/reference/countries/", response=list[ReferenceCountryOut])
async def list_reference_countries(request):
    """Return supported countries for public forms and client onboarding."""

    return get_countries()


@router.get(
    "/reference/countries/{country_code}/states/",
    response=list[ReferenceStateOut],
)
async def list_reference_states(request, country_code: str):
    """Return states for a supported country."""

    try:
        normalized_country = validate_country_code(country_code)
    except DjangoValidationError as exc:
        raise _as_http_error(exc) from exc
    return get_states(normalized_country)


@router.get(
    "/reference/countries/{country_code}/states/{state_code}/lgas/",
    response=list[ReferenceLgaOut],
)
async def list_reference_lgas(request, country_code: str, state_code: str):
    """Return local government areas for a country/state pair."""

    try:
        normalized_country = validate_country_code(country_code)
        normalized_state = validate_state_code(normalized_country, state_code)
    except DjangoValidationError as exc:
        raise _as_http_error(exc) from exc
    return get_lgas(normalized_country, normalized_state)


@router.get(
    "/reference/countries/{country_code}/cities/",
    response=list[ReferenceCityOut],
)
async def list_reference_cities(
    request,
    country_code: str,
    state: str | None = Query(default=None),
    lga: str | None = Query(default=None),
):
    """Return cities/wards for a country with optional state/LGA filters."""

    try:
        normalized_country = validate_country_code(country_code)
        normalized_state = (
            validate_state_code(normalized_country, state) if state else None
        )
        normalized_lga = (
            validate_lga_code(normalized_country, normalized_state, lga)
            if lga and normalized_state
            else None
        )
    except DjangoValidationError as exc:
        raise _as_http_error(exc) from exc

    return get_cities(
        normalized_country,
        state_ref=normalized_state,
        lga_ref=normalized_lga,
    )


@router.get("/reference/banks/", response=list[ReferenceBankOut])
async def list_reference_banks(
    request,
    country: str = Query(default="NG"),
):
    """Return supported banks for the selected country."""

    try:
        normalized_country = validate_country_code(country)
    except DjangoValidationError as exc:
        raise _as_http_error(exc) from exc
    return get_banks(normalized_country)
