# apps/measurements/apis/sync/measurement_views.py
"""
DRF synchronous views for the Measurements domain.

Endpoints:
  GET    /api/v1/measurements/               — List user's profiles
  POST   /api/v1/measurements/               — Create new profile
  GET    /api/v1/measurements/<id>/          — Detail
  PUT    /api/v1/measurements/<id>/          — Full update
  PATCH  /api/v1/measurements/<id>/          — Partial update
  DELETE /api/v1/measurements/<id>/          — Delete
  POST   /api/v1/measurements/<id>/set-default/ — Set as default
"""

import logging

from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.renderers import BrowsableAPIRenderer
from rest_framework.views import APIView

from apps.common.renderers import CustomJSONRenderer, success_response, error_response
from apps.common.permissions import IsAuthenticatedAndActive
from apps.measurements.selectors import (
    get_user_profiles,
    get_profile_by_id,
)
from apps.measurements.serializers import (
    MeasurementProfileSerializer,
    MeasurementProfileWriteSerializer,
)
from apps.measurements.services import (
    create_measurement_profile,
    create_mirrorsize_browser_session,
    update_measurement_profile,
    delete_measurement_profile,
    import_mirrorsize_browser_measurement,
    set_default_profile,
)
from apps.measurements.services.measurement_service import (
    MeasurementProfileLimitError,
    MirrorSizeProviderError,
)
from django.core.exceptions import PermissionDenied

logger = logging.getLogger(__name__)

_RENDERERS = [CustomJSONRenderer, BrowsableAPIRenderer]


class MeasurementProfileListCreateView(APIView):
    """
    GET  /api/v1/measurements/ — List all profiles for the authenticated user.
    POST /api/v1/measurements/ — Create a new measurement profile.
    """
    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def get(self, request):
        profiles = get_user_profiles(request.user)
        return success_response(
            data=MeasurementProfileSerializer(profiles, many=True).data
        )

    def post(self, request):
        serializer = MeasurementProfileWriteSerializer(data=request.data)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        vd = serializer.validated_data
        try:
            profile = create_measurement_profile(
                owner=request.user,
                name=vd.get("name", "My Measurements"),
                data=serializer.to_model_data(vd),
                set_as_default=vd.get("set_as_default", False),
            )
        except MeasurementProfileLimitError as exc:
            return error_response(message=str(exc), status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return success_response(
            data=MeasurementProfileSerializer(profile).data,
            message="Measurement profile created.",
            status=status.HTTP_201_CREATED,
        )


class MeasurementProfileDetailView(APIView):
    """
    GET    /api/v1/measurements/<id>/
    PUT    /api/v1/measurements/<id>/
    PATCH  /api/v1/measurements/<id>/
    DELETE /api/v1/measurements/<id>/
    """
    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def get(self, request, profile_id):
        profile = get_profile_by_id(profile_id=profile_id, user=request.user)
        if not profile:
            return error_response(message="Profile not found.", status=status.HTTP_404_NOT_FOUND)
        return success_response(data=MeasurementProfileSerializer(profile).data)

    def _update(self, request, profile_id, partial: bool):
        serializer = MeasurementProfileWriteSerializer(data=request.data, partial=partial)
        if not serializer.is_valid():
            return error_response(
                message="Validation error.",
                status=status.HTTP_400_BAD_REQUEST,
                errors=serializer.errors,
            )
        vd = serializer.validated_data
        try:
            profile = update_measurement_profile(
                profile_id=profile_id,
                owner=request.user,
                data=serializer.to_model_data(vd),
            )
        except PermissionDenied as exc:
            return error_response(message=str(exc), status=status.HTTP_404_NOT_FOUND)

        return success_response(
            data=MeasurementProfileSerializer(profile).data,
            message="Profile updated.",
        )

    def put(self, request, profile_id):
        return self._update(request, profile_id, partial=False)

    def patch(self, request, profile_id):
        return self._update(request, profile_id, partial=True)

    def delete(self, request, profile_id):
        try:
            delete_measurement_profile(profile_id=profile_id, owner=request.user)
        except PermissionDenied as exc:
            return error_response(message=str(exc), status=status.HTTP_404_NOT_FOUND)
        return success_response(message="Measurement profile deleted.", status=status.HTTP_204_NO_CONTENT)


class SetDefaultProfileView(APIView):
    """POST /api/v1/measurements/<id>/set-default/"""
    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request, profile_id):
        try:
            profile = set_default_profile(profile_id=profile_id, owner=request.user)
        except PermissionDenied as exc:
            return error_response(message=str(exc), status=status.HTTP_404_NOT_FOUND)
        return success_response(
            data=MeasurementProfileSerializer(profile).data,
            message="Default profile updated.",
        )


class MirrorSizeBrowserSessionView(APIView):
    """Create a MirrorSize mobile-browser access session.

    The endpoint keeps the MirrorSize API key server-side and delegates all
    external traffic to the provider wrapper backed by ``apps.common.http``.
    """

    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request):
        try:
            session = create_mirrorsize_browser_session(
                user=request.user,
                name=request.data.get("name", ""),
                email=request.data.get("email", ""),
                mobile_no=request.data.get("mobile_no", ""),
            )
        except MirrorSizeProviderError as exc:
            return error_response(message=str(exc), status=status.HTTP_502_BAD_GATEWAY)

        return success_response(
            data=session,
            message="MirrorSize measurement session created.",
            status=status.HTTP_201_CREATED,
        )


class MirrorSizeImportView(APIView):
    """Import a completed MirrorSize mobile-browser measurement profile."""

    renderer_classes = _RENDERERS
    permission_classes = [IsAuthenticated, IsAuthenticatedAndActive]

    def post(self, request):
        access_code = str(request.data.get("access_code", "")).strip()
        if not access_code:
            return error_response(
                message="access_code is required.",
                status=status.HTTP_400_BAD_REQUEST,
            )
        try:
            profile = import_mirrorsize_browser_measurement(
                user=request.user,
                access_code=access_code,
                set_as_default=bool(request.data.get("set_as_default", True)),
            )
        except MirrorSizeProviderError as exc:
            return error_response(message=str(exc), status=status.HTTP_502_BAD_GATEWAY)
        except MeasurementProfileLimitError as exc:
            return error_response(message=str(exc), status=status.HTTP_422_UNPROCESSABLE_ENTITY)

        return success_response(
            data=MeasurementProfileSerializer(profile).data,
            message="MirrorSize measurements imported.",
        )
