"""Read-only reference data endpoints for web and mobile clients."""

from __future__ import annotations

from rest_framework import generics, status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

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


class ReferenceCountriesView(generics.GenericAPIView):
    serializer_class = ReferenceCountrySerializer
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs) -> Response:
        serializer = self.get_serializer(get_countries(), many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ReferenceStatesView(generics.GenericAPIView):
    serializer_class = ReferenceStateSerializer
    permission_classes = [AllowAny]

    def get(self, request, country_code: str, *args, **kwargs) -> Response:
        path_serializer = CountryPathSerializer(data={"country_code": country_code})
        path_serializer.is_valid(raise_exception=True)
        states = get_states(path_serializer.validated_data["country_code"])
        serializer = self.get_serializer(states, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ReferenceLgasView(generics.GenericAPIView):
    serializer_class = ReferenceLgaSerializer
    permission_classes = [AllowAny]

    def get(
        self, request, country_code: str, state_code: str, *args, **kwargs
    ) -> Response:
        path_serializer = StatePathSerializer(
            data={"country_code": country_code, "state_code": state_code}
        )
        path_serializer.is_valid(raise_exception=True)
        lgas = get_lgas(
            path_serializer.validated_data["country_code"],
            path_serializer.validated_data["state_code"],
        )
        serializer = self.get_serializer(lgas, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)


class ReferenceCitiesView(generics.GenericAPIView):
    serializer_class = ReferenceCitySerializer
    permission_classes = [AllowAny]

    def get(self, request, country_code: str, *args, **kwargs) -> Response:
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
        return Response(serializer.data, status=status.HTTP_200_OK)


class ReferenceStateLgaCitiesView(generics.GenericAPIView):
    serializer_class = ReferenceCitySerializer
    permission_classes = [AllowAny]

    def get(
        self,
        request,
        country_code: str,
        state_code: str,
        lga_code: str,
        *args,
        **kwargs,
    ) -> Response:
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
        return Response(serializer.data, status=status.HTTP_200_OK)


class ReferenceBanksView(generics.GenericAPIView):
    serializer_class = ReferenceBankSerializer
    permission_classes = [AllowAny]

    def get(self, request, *args, **kwargs) -> Response:
        query_serializer = BankQuerySerializer(
            data={"country": request.query_params.get("country", "NG")}
        )
        query_serializer.is_valid(raise_exception=True)
        banks = get_banks(query_serializer.validated_data["country"])
        serializer = self.get_serializer(banks, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @extend_schema(
        summary="List cities in an LGA",
        description="Returns cities for the specific country, state, and LGA path.",
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
            data=serializer.data, message="Cities retrieved successfully."
        )


# ===========================================================================
# FINANCIAL INSTITUTIONS
# ===========================================================================


class ReferenceBanksView(generics.GenericAPIView):
    """
    GET /api/v1/reference/banks/

    Returns a list of banks for a given country for transfer operations.
    """

    serializer_class = ReferenceBankSerializer
    permission_classes = [AllowAny]
    renderer_classes = [CustomJSONRenderer, BrowsableAPIRenderer]

    @extend_schema(
        summary="List banks",
        description="Returns a list of banks for the specified country (default: NG).",
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
            data=serializer.data, message="Banks retrieved successfully."
        )
