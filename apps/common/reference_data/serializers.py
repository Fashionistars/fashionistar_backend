"""DRF serializers for common reference data."""

from __future__ import annotations

from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers

from apps.common.reference_data.validators import (
    validate_bank_code,
    validate_city_or_custom_city,
    validate_country_code,
    validate_lga_code,
    validate_state_code,
    validate_street_address,
)


def _raise_drf(exc: DjangoValidationError) -> None:
    raise serializers.ValidationError(exc.messages)


class ReferenceCountrySerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    flag = serializers.CharField(allow_blank=True)
    phone_code = serializers.CharField()
    is_active = serializers.BooleanField()


class ReferenceStateSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    country_code = serializers.CharField()
    is_active = serializers.BooleanField()


class ReferenceLgaSerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    state_code = serializers.CharField()
    country_code = serializers.CharField()
    is_active = serializers.BooleanField()


class ReferenceCitySerializer(serializers.Serializer):
    code = serializers.CharField()
    name = serializers.CharField()
    lga_code = serializers.CharField()
    state_code = serializers.CharField()
    country_code = serializers.CharField()
    latitude = serializers.FloatField(allow_null=True)
    longitude = serializers.FloatField(allow_null=True)
    is_active = serializers.BooleanField()


class ReferenceBankSerializer(serializers.Serializer):
    id = serializers.CharField()
    code = serializers.CharField()
    name = serializers.CharField()
    country_code = serializers.CharField()
    currency = serializers.CharField()
    provider = serializers.CharField()
    is_active = serializers.BooleanField()


class CountryPathSerializer(serializers.Serializer):
    country_code = serializers.CharField(max_length=2)

    def validate_country_code(self, value: str) -> str:
        try:
            return validate_country_code(value)
        except DjangoValidationError as exc:
            _raise_drf(exc)


class StatePathSerializer(CountryPathSerializer):
    state_code = serializers.CharField(max_length=80)

    def validate(self, attrs: dict) -> dict:
        try:
            attrs["state_code"] = validate_state_code(attrs["country_code"], attrs["state_code"])
        except DjangoValidationError as exc:
            _raise_drf(exc)
        return attrs


class LgaPathSerializer(StatePathSerializer):
    lga_code = serializers.CharField(max_length=100)

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        try:
            attrs["lga_code"] = validate_lga_code(
                attrs["country_code"],
                attrs["state_code"],
                attrs["lga_code"],
            )
        except DjangoValidationError as exc:
            _raise_drf(exc)
        return attrs


class CitiesQuerySerializer(CountryPathSerializer):
    state = serializers.CharField(required=False, allow_blank=True, max_length=80)
    lga = serializers.CharField(required=False, allow_blank=True, max_length=100)

    def validate(self, attrs: dict) -> dict:
        attrs = super().validate(attrs)
        state = attrs.get("state")
        lga = attrs.get("lga")
        try:
            if state:
                attrs["state"] = validate_state_code(attrs["country_code"], state)
            if lga and state:
                attrs["lga"] = validate_lga_code(attrs["country_code"], attrs["state"], lga)
        except DjangoValidationError as exc:
            _raise_drf(exc)
        return attrs


class BankQuerySerializer(serializers.Serializer):
    country = serializers.CharField(default="NG", max_length=2)

    def validate_country(self, value: str) -> str:
        try:
            return validate_country_code(value)
        except DjangoValidationError as exc:
            _raise_drf(exc)


class AddressReferenceInputSerializer(serializers.Serializer):
    country_code = serializers.CharField(max_length=2)
    state_code = serializers.CharField(max_length=80)
    lga_code = serializers.CharField(max_length=100)
    city_code = serializers.CharField(required=False, allow_blank=True, max_length=100)
    custom_city = serializers.CharField(required=False, allow_blank=True, max_length=80)
    street_address = serializers.CharField(max_length=180)

    def validate(self, attrs: dict) -> dict:
        try:
            attrs["country_code"] = validate_country_code(attrs["country_code"])
            attrs["state_code"] = validate_state_code(attrs["country_code"], attrs["state_code"])
            attrs["lga_code"] = validate_lga_code(
                attrs["country_code"],
                attrs["state_code"],
                attrs["lga_code"],
            )
            city_result = validate_city_or_custom_city(
                attrs["country_code"],
                attrs["state_code"],
                attrs["lga_code"],
                attrs.get("city_code"),
                attrs.get("custom_city"),
            )
            attrs.update(city_result)
            attrs["street_address"] = validate_street_address(attrs["street_address"])
        except DjangoValidationError as exc:
            _raise_drf(exc)
        return attrs


class BankReferenceInputSerializer(serializers.Serializer):
    country_code = serializers.CharField(default="NG", max_length=2)
    bank_code = serializers.CharField(max_length=20)

    def validate(self, attrs: dict) -> dict:
        try:
            attrs["country_code"] = validate_country_code(attrs["country_code"])
            attrs["bank_code"] = validate_bank_code(attrs["bank_code"], attrs["country_code"])
        except DjangoValidationError as exc:
            _raise_drf(exc)
        return attrs

