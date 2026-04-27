# apps/measurements/selectors/measurement_selectors.py
"""
Read-only queries for the Measurements domain.
"""
from django.db.models import QuerySet
from apps.measurements.models import MeasurementProfile


def get_user_profiles(user_id) -> QuerySet:
    """Return all measurement profiles for a user, default first."""
    return MeasurementProfile.objects.filter(
        owner_id=user_id,
    ).order_by("-is_default", "-updated_at")


def get_default_profile(user_id) -> MeasurementProfile | None:
    """Return the user's default measurement profile, or None."""
    return MeasurementProfile.objects.filter(
        owner_id=user_id,
        is_default=True,
    ).first()


def get_profile_by_id(profile_id, user_id) -> MeasurementProfile | None:
    """Return a profile by ID, scoped to the requesting user."""
    return MeasurementProfile.objects.filter(
        id=profile_id,
        owner_id=user_id,
    ).first()
