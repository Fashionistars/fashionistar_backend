# apps/authentication/tests/unit/conftest.py
"""
Unit Test Conftest
==================
Overrides the app-level autouse `mock_otp_generation` fixture
for the `unit/` package specifically.

Without this override, the parent conftest.py `mock_otp_generation`
(autouse=True) patches OTPService.generate_otp_sync BEFORE the unit
tests can import and call the real service — making it impossible
to test the actual OTPService logic.

This local conftest disables that patch for the unit test package only
by redefining the same fixture name with a no-op body.
"""
import pytest


@pytest.fixture(autouse=True)
def mock_otp_generation(mocker):
    """
    OVERRIDE: Do NOT patch OTPService.generate_otp_sync in unit tests.
    Unit tests mock Redis themselves and call the real service methods.
    Returning an empty dict (no entries stored) satisfies the type.
    """
    return {}


@pytest.fixture(autouse=True)
def no_throttle(mocker):
    """Inherit throttle bypass for unit tests too."""
    mocker.patch(
        'apps.authentication.throttles.BurstRateThrottle.allow_request',
        return_value=True,
    )
    mocker.patch(
        'apps.authentication.throttles.SustainedRateThrottle.allow_request',
        return_value=True,
    )
