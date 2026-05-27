# apps/measurements/admin_backend/selectors.py
from __future__ import annotations
import logging
from typing import Optional, Dict, Any, List
from django.db.models import Q, QuerySet
from apps.measurements.models.measurement import MeasurementProfile

logger = logging.getLogger(__name__)

class AdminMeasurementSelector:
    @staticmethod
    def get_measurements_queryset(filters: Optional[Dict[str, Any]] = None) -> QuerySet[MeasurementProfile]:
        """
        Builds optimized query for MeasurementProfile.
        """
        queryset = MeasurementProfile.objects.select_related("owner", "verified_by")
        if not filters:
            return queryset
            
        is_verified = filters.get("is_verified")
        if is_verified is not None:
            queryset = queryset.filter(is_verified=is_verified)
            
        search = filters.get("search")
        if search:
            queryset = queryset.filter(
                Q(name__icontains=search) |
                Q(owner__email__icontains=search)
            )
            
        return queryset

    @classmethod
    async def aget_measurements_list(cls, filters: Optional[Dict[str, Any]] = None) -> List[MeasurementProfile]:
        """
        Asynchronously fetches measurements list.
        """
        qs = cls.get_measurements_queryset(filters)
        return [profile async for profile in qs]

    @classmethod
    async def aget_measurement_detail(cls, profile_id: str) -> MeasurementProfile:
        """
        Asynchronously retrieves detailed measurement profile.
        """
        return await MeasurementProfile.objects.select_related("owner", "verified_by").aget(id=profile_id)
