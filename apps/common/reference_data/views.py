"""Read-only reference data endpoints for web and mobile clients."""

from __future__ import annotations

from drf_spectacular.utils import extend_schema
from rest_framework import generics
from rest_framework.permissions import AllowAny
from rest_framework.renderers import BrowsableAPIRenderer

from apps.common.renderers import CustomJSONRenderer
from apps.common.responses import success_response
from apps.common.reference_data.banks import get_banks
from apps.common.reference_data.countries import get_countries
from apps.common.reference_data.locations import get_cities, get_lgas, get_states
from apps.common.reference_data.serializers import (
    BankQuerySerializer,
    CitiesQuerySerializer,
    CountryPathSerializer,
    LgaPathSerializer,
    ReferenceBankSerializer,
    ReferenceCitySerializer,
    ReferenceCountrySerializer,
    ReferenceLgaSerializer,
    ReferenceStateSerializer,
    StatePathSerializer,
)


class ReferenceBaseView(generics.GenericAPIView):
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]


class ReferenceCountriesView(ReferenceBaseView):
    serializer_class = ReferenceCountrySerializer

    @extend_schema(
        summary="List supported countries",
        description="Returns static supported country metadata for web, admin, and mobile clients.",
        responses={200: ReferenceCountrySerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        serializer = self.get_serializer(get_countries(), many=True)
        return success_response(
            data=serializer.data,
            message="Countries retrieved successfully.",
        )


class ReferenceStatesView(ReferenceBaseView):
    serializer_class = ReferenceStateSerializer

    @extend_schema(
        summary="List states for a country",
        description="Returns states configured for the selected country.",
        responses={200: ReferenceStateSerializer(many=True)},
    )
    def get(self, request, country_code: str, *args, **kwargs):
        path_serializer = CountryPathSerializer(data={"country_code": country_code})
        path_serializer.is_valid(raise_exception=True)
        states = get_states(path_serializer.validated_data["country_code"])
        serializer = self.get_serializer(states, many=True)
        return success_response(
            data=serializer.data,
            message="States retrieved successfully.",
        )


class ReferenceLgasView(ReferenceBaseView):
    serializer_class = ReferenceLgaSerializer

    @extend_schema(
        summary="List LGAs for a state",
        description="Returns local government areas for the selected country and state.",
        responses={200: ReferenceLgaSerializer(many=True)},
    )
    def get(self, request, country_code: str, state_code: str, *args, **kwargs):
        path_serializer = StatePathSerializer(
            data={"country_code": country_code, "state_code": state_code}
        )
        path_serializer.is_valid(raise_exception=True)
        lgas = get_lgas(
            path_serializer.validated_data["country_code"],
            path_serializer.validated_data["state_code"],
        )
        serializer = self.get_serializer(lgas, many=True)
        return success_response(
            data=serializer.data,
            message="Local governments retrieved successfully.",
        )


class ReferenceCitiesView(ReferenceBaseView):
    serializer_class = ReferenceCitySerializer

    @extend_schema(
        summary="List cities for a country",
        description="Returns cities for the selected country, optionally filtered by state and LGA.",
        responses={200: ReferenceCitySerializer(many=True)},
    )
    def get(self, request, country_code: str, *args, **kwargs):
        query_serializer = CitiesQuerySerializer(
            data={
                "country_code": country_code,
                "state": request.query_params.get("state", ""),
                "lga": request.query_params.get("lga", ""),
            }
        )
        query_serializer.is_valid(raise_exception=True)
        cities = get_cities(
            query_serializer.validated_data["country_code"],
            state_ref=query_serializer.validated_data.get("state") or None,
            lga_ref=query_serializer.validated_data.get("lga") or None,
        )
        serializer = self.get_serializer(cities, many=True)
        return success_response(
            data=serializer.data,
            message="Cities retrieved successfully.",
        )


class ReferenceStateLgaCitiesView(ReferenceBaseView):
    serializer_class = ReferenceCitySerializer

    @extend_schema(
        summary="List cities in an LGA",
        description="Returns cities for the selected country, state, and LGA.",
        responses={200: ReferenceCitySerializer(many=True)},
    )
    def get(
        self,
        request,
        country_code: str,
        state_code: str,
        lga_code: str,
        *args,
        **kwargs,
    ):
        path_serializer = LgaPathSerializer(
            data={
                "country_code": country_code,
                "state_code": state_code,
                "lga_code": lga_code,
            }
        )
        path_serializer.is_valid(raise_exception=True)
        cities = get_cities(
            path_serializer.validated_data["country_code"],
            state_ref=path_serializer.validated_data["state_code"],
            lga_ref=path_serializer.validated_data["lga_code"],
        )
        serializer = self.get_serializer(cities, many=True)
        return success_response(
            data=serializer.data,
            message="Cities retrieved successfully.",
        )


class ReferenceBanksView(ReferenceBaseView):
    serializer_class = ReferenceBankSerializer

    @extend_schema(
        summary="List banks",
        description="Returns banks for the specified country. Nigeria defaults to Paystack-backed bank metadata.",
        responses={200: ReferenceBankSerializer(many=True)},
    )
    def get(self, request, *args, **kwargs):
        query_serializer = BankQuerySerializer(
            data={"country": request.query_params.get("country", "NG")}
        )
        query_serializer.is_valid(raise_exception=True)
        banks = get_banks(query_serializer.validated_data["country"])
        serializer = self.get_serializer(banks, many=True)
        return success_response(
            data=serializer.data,
            message="Banks retrieved successfully.",
        )
