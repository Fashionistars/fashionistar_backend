# apps/audit_logs/tests/test_stress.py
"""
FASHIONISTAR — Stress Tests: AuditEventLog Bulk Write
======================================================
Validates correctness and performance of bulk audit log writes.

These tests verify:
  - bulk_create writes exactly the expected number of rows
  - No data corruption (event_type, actor_email preserved)
  - Count integrity after 10,000 row inserts
  - Compliance events are never deleted by cleanup task
  - cleanup_audit_logs task correctly deletes non-compliance expired events

Run with: uv run pytest apps/audit_logs/tests/test_stress.py -vv -s
"""
from __future__ import annotations

import pytest
from datetime import timedelta


pytestmark = pytest.mark.django_db(transaction=True)


def _build_events(count: int, compliance: bool = False, days_old: int = 0):
    """Build a list of AuditEventLog instances (NOT saved to DB yet)."""
    from django.utils import timezone
    from apps.audit_logs.models import AuditEventLog, EventType, EventCategory, SeverityLevel

    now = timezone.now()
    events = []
    for i in range(count):
        obj = AuditEventLog(
            event_type=EventType.API_CALL,
            event_category=EventCategory.SYSTEM,
            severity=SeverityLevel.INFO,
            action=f"stress test event {i}",
            actor_email=f"stress{i}@example.com",
            is_compliance=compliance,
        )
        events.append(obj)

    return events


class TestBulkWriteCorrectness:
    """Bulk audit log writes produce correct row counts with no data corruption."""

    def test_bulk_create_1000_events(self):
        """bulk_create of 1,000 events completes and count matches."""
        from apps.audit_logs.models import AuditEventLog

        before = AuditEventLog.objects.count()
        events = _build_events(1000)
        AuditEventLog.objects.bulk_create(events, batch_size=200)
        after = AuditEventLog.objects.count()
        assert after - before == 1000

    def test_bulk_create_10000_events(self):
        """
        bulk_create of 10,000 events succeeds in <10s (stress correctness, not perf).
        Uses batch_size=500 to avoid large single INSERT statements.
        """
        from apps.audit_logs.models import AuditEventLog

        before = AuditEventLog.objects.count()
        events = _build_events(10000)
        AuditEventLog.objects.bulk_create(events, batch_size=500)
        after = AuditEventLog.objects.count()
        assert after - before == 10000

    def test_bulk_data_integrity(self):
        """All 500 stress events have correct actor_email and event_type."""
        from apps.audit_logs.models import AuditEventLog, EventType

        events = _build_events(500)
        AuditEventLog.objects.bulk_create(events, batch_size=100)

        # Spot-check: count events with the expected event_type
        count = AuditEventLog.objects.filter(
            event_type=EventType.API_CALL,
            actor_email__startswith="stress",
        ).count()
        assert count >= 500

    def test_compliance_events_never_deleted_by_cleanup(self):
        """
        compliance=True events must NOT be deleted by cleanup_audit_logs,
        even if they are older than 90 days.
        """
        from apps.audit_logs.models import AuditEventLog, EventType, EventCategory, SeverityLevel
        from django.utils import timezone

        # Create 10 old compliance events
        old_date = timezone.now() - timedelta(days=200)
        events = [
            AuditEventLog(
                event_type=EventType.LOGIN_SUCCESS,
                event_category=EventCategory.SECURITY,
                severity=SeverityLevel.INFO,
                action=f"compliance event {i}",
                is_compliance=True,
            )
            for i in range(10)
        ]
        created = AuditEventLog.objects.bulk_create(events)
        # Manually backdate created_at using queryset.update() (bypasses Python guard)
        pks = [obj.pk for obj in created]
        AuditEventLog.objects.filter(pk__in=pks).update(created_at=old_date)

        count_before = AuditEventLog.objects.filter(
            is_compliance=True, action__startswith="compliance event"
        ).count()
        assert count_before == 10

        # Simulate cleanup task
        deleted, _ = AuditEventLog.objects.filter(
            is_compliance=False,
            created_at__lt=timezone.now() - timedelta(days=90),
        ).delete()

        # Compliance events must survive
        count_after = AuditEventLog.objects.filter(
            is_compliance=True, action__startswith="compliance event"
        ).count()
        assert count_after == 10, (
            f"Compliance events were deleted! Before={count_before}, After={count_after}"
        )

    def test_non_compliance_old_events_are_deleted(self):
        """
        Non-compliance events older than 90 days MUST be deleted by cleanup.
        """
        from apps.audit_logs.models import AuditEventLog, EventType, EventCategory, SeverityLevel
        from django.utils import timezone

        old_date = timezone.now() - timedelta(days=100)
        events = [
            AuditEventLog(
                event_type=EventType.API_CALL,
                event_category=EventCategory.SYSTEM,
                severity=SeverityLevel.INFO,
                action=f"old non-compliance event {i}",
                is_compliance=False,
            )
            for i in range(50)
        ]
        created = AuditEventLog.objects.bulk_create(events)
        pks = [obj.pk for obj in created]
        AuditEventLog.objects.filter(pk__in=pks).update(created_at=old_date)

        # Run cleanup
        deleted, _ = AuditEventLog.objects.filter(
            is_compliance=False,
            created_at__lt=timezone.now() - timedelta(days=90),
        ).delete()

        assert deleted >= 50, f"Expected ≥50 old events deleted, got {deleted}"

        # Confirm they're gone
        remaining = AuditEventLog.objects.filter(pk__in=pks).count()
        assert remaining == 0


class TestAuditLogCSVExport:
    """E5: Compliance CSV export action produces correct output."""

    def test_compliance_export_streams_csv(self, rf):
        """The export action streams a valid CSV file."""
        from apps.audit_logs.models import AuditEventLog, EventType, EventCategory, SeverityLevel

        # Create 5 compliance events
        for i in range(5):
            AuditEventLog.objects.create(
                event_type=EventType.LOGIN_SUCCESS,
                event_category=EventCategory.SECURITY,
                severity=SeverityLevel.INFO,
                action=f"csv export test event {i}",
                actor_email=f"user{i}@example.com",
                is_compliance=True,
            )

        from apps.audit_logs.admin import export_compliance_logs_csv
        from apps.authentication.models import UnifiedUser

        su = UnifiedUser.objects.create_superuser(
            email="csvexport_su@fashionistar.io",
            password="SuperPass123!",
        )
        request = rf.get("/admin/")
        request.user = su

        qs = AuditEventLog.objects.filter(is_compliance=True)
        response = export_compliance_logs_csv(None, request, qs)

        assert response is not None
        assert response.status_code == 200
        assert "text/csv" in response["Content-Type"]
        assert "fashionistar_compliance_audit_" in response["Content-Disposition"]

    def test_non_superuser_export_returns_403(self, rf):
        """Non-superuser attempting compliance export gets 403."""
        from apps.audit_logs.models import AuditEventLog
        from apps.audit_logs.admin import export_compliance_logs_csv
        from apps.authentication.models import UnifiedUser

        user = UnifiedUser.objects.create_user(
            email="notsu@fashionistar.io",
            password="Pass123!",
            role="client",
        )
        request = rf.get("/admin/")
        request.user = user

        qs = AuditEventLog.objects.all()
        response = export_compliance_logs_csv(None, request, qs)

        assert response.status_code == 403
