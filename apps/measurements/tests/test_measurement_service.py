# apps/measurements/tests/test_measurement_service.py
"""
Unit tests for the Measurements domain service layer.

Coverage:
  - create_measurement_profile: happy path, limit enforcement
  - update_measurement_profile: ownership validation
  - delete_measurement_profile: default promotion
  - set_default_profile: atomicity
  - assert_buyer_has_measurement: checkout gate
"""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied

from apps.measurements.models import MeasurementProfile
from apps.measurements.services import (
    create_measurement_profile,
    update_measurement_profile,
    delete_measurement_profile,
    set_default_profile,
    assert_buyer_has_measurement,
)
from apps.measurements.services.measurement_service import (
    MeasurementRequiredError,
    MeasurementProfileLimitError,
    MAX_PROFILES_PER_USER,
)

User = get_user_model()
pytestmark = pytest.mark.django_db


# ─────────────────────────────────────────────────────────────────────────────
# FIXTURES
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def buyer(db):
    return User.objects.create_user(email="buyer@test.com", password="Pass1234!")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(email="other@test.com", password="Pass1234!")


def _make_full_profile(user, name="Default", is_default=True):
    """Create a profile with all core measurements filled."""
    return MeasurementProfile.objects.create(
        owner=user,
        name=name,
        is_default=is_default,
        bust=90,
        waist=70,
        hips=95,
        height=165,
    )


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: create_measurement_profile
# ─────────────────────────────────────────────────────────────────────────────

class TestCreateMeasurementProfile:
    def test_creates_profile_and_sets_default_for_first_profile(self, buyer):
        profile = create_measurement_profile(
            owner=buyer,
            name="My Measurements",
            data={"bust": 88, "waist": 68, "hips": 92, "height": 162},
        )
        assert profile.is_default is True
        assert profile.owner == buyer

    def test_second_profile_does_not_override_default_unless_requested(self, buyer):
        create_measurement_profile(
            owner=buyer,
            name="Profile 1",
            data={"bust": 88, "waist": 68, "hips": 92, "height": 162},
        )
        second = create_measurement_profile(
            owner=buyer,
            name="Profile 2",
            data={"waist": 70},
            set_as_default=False,
        )
        assert second.is_default is False
        default = MeasurementProfile.objects.get(owner=buyer, is_default=True)
        assert default.name == "Profile 1"

    def test_set_as_default_updates_previous_default(self, buyer):
        create_measurement_profile(
            owner=buyer,
            name="Profile 1",
            data={},
        )
        second = create_measurement_profile(
            owner=buyer,
            name="Profile 2",
            data={},
            set_as_default=True,
        )
        assert second.is_default is True
        assert not MeasurementProfile.objects.filter(
            owner=buyer, name="Profile 1", is_default=True
        ).exists()

    def test_raises_limit_error_at_max_profiles(self, buyer):
        for i in range(MAX_PROFILES_PER_USER):
            create_measurement_profile(
                owner=buyer,
                name=f"Profile {i}",
                data={},
            )
        with pytest.raises(MeasurementProfileLimitError):
            create_measurement_profile(owner=buyer, name="Extra", data={})


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: update_measurement_profile
# ─────────────────────────────────────────────────────────────────────────────

class TestUpdateMeasurementProfile:
    def test_updates_measurements_correctly(self, buyer):
        profile = _make_full_profile(buyer)
        updated = update_measurement_profile(
            profile_id=profile.id,
            owner=buyer,
            data={"waist": 72.5},
        )
        assert float(updated.waist) == 72.5

    def test_raises_permission_denied_for_wrong_owner(self, buyer, other_user):
        profile = _make_full_profile(buyer)
        with pytest.raises(PermissionDenied):
            update_measurement_profile(
                profile_id=profile.id,
                owner=other_user,
                data={"waist": 72},
            )


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: delete_measurement_profile
# ─────────────────────────────────────────────────────────────────────────────

class TestDeleteMeasurementProfile:
    def test_deletes_profile(self, buyer):
        profile = _make_full_profile(buyer)
        delete_measurement_profile(profile_id=profile.id, owner=buyer)
        assert not MeasurementProfile.objects.filter(id=profile.id).exists()

    def test_promotes_next_profile_to_default_after_deletion(self, buyer):
        default_profile = _make_full_profile(buyer, name="Default")
        second = create_measurement_profile(
            owner=buyer, name="Second", data={"waist": 70}, set_as_default=False,
        )
        delete_measurement_profile(profile_id=default_profile.id, owner=buyer)
        second.refresh_from_db()
        assert second.is_default is True

    def test_raises_permission_denied_for_wrong_owner(self, buyer, other_user):
        profile = _make_full_profile(buyer)
        with pytest.raises(PermissionDenied):
            delete_measurement_profile(profile_id=profile.id, owner=other_user)


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: checkout gate — assert_buyer_has_measurement
# ─────────────────────────────────────────────────────────────────────────────

class TestAssertBuyerHasMeasurement:
    def test_passes_when_default_profile_with_core_measurements(self, buyer):
        _make_full_profile(buyer)
        profile = assert_buyer_has_measurement(buyer)
        assert profile.has_core_measurements is True

    def test_raises_when_no_profiles_exist(self, buyer):
        with pytest.raises(MeasurementRequiredError):
            assert_buyer_has_measurement(buyer)

    def test_raises_when_profile_missing_core_measurements(self, buyer):
        # Profile exists but waist/hips/height missing
        MeasurementProfile.objects.create(
            owner=buyer,
            name="Incomplete",
            is_default=True,
            bust=90,
            # waist, hips, height all NULL
        )
        with pytest.raises(MeasurementRequiredError):
            assert_buyer_has_measurement(buyer)

    def test_falls_back_to_any_profile_if_no_default(self, buyer):
        """If user has a profile but no default flag, should still work."""
        MeasurementProfile.objects.create(
            owner=buyer,
            name="No Default",
            is_default=False,  # No default flag
            bust=90,
            waist=70,
            hips=95,
            height=165,
        )
        result = assert_buyer_has_measurement(buyer)
        assert result.has_core_measurements is True


# ─────────────────────────────────────────────────────────────────────────────
# TESTS: set_default_profile
# ─────────────────────────────────────────────────────────────────────────────

class TestSetDefaultProfile:
    def test_atomically_clears_old_default(self, buyer):
        p1 = _make_full_profile(buyer, name="P1")
        p2 = create_measurement_profile(
            owner=buyer, name="P2", data={}, set_as_default=False
        )
        set_default_profile(profile_id=p2.id, owner=buyer)
        p1.refresh_from_db()
        p2.refresh_from_db()
        assert p2.is_default is True
        assert p1.is_default is False
