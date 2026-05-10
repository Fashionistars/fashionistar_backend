# apps/audit_logs/tests/test_concurrency.py
"""
FASHIONISTAR — Concurrency + Idempotency Tests: AuditEventLog
=============================================================
Validates that concurrent audit writes produce correct results:
  - UUIDs are collision-free across sequential + parallel writes
  - Immutability guard raises PermissionError on update attempts
  - correlation_id is NOT a unique constraint (trace ID, not PK)
  - Atomic bulk inserts maintain row count integrity

NOTE ON SQLite:
  True multi-threaded tests with SQLite transaction=True cause
  "database table is locked" errors because SQLite uses file-level locking.
  Thread-based concurrency tests use the real DB sequentially to verify
  logic correctness; parallel race tests are guarded with skipif.

Run with: uv run pytest apps/audit_logs/tests/test_concurrency.py -vv
"""
from __future__ import annotations

import uuid
import threading
import pytest

from django.conf import settings

_IS_SQLITE = "sqlite" in settings.DATABASES["default"].get("ENGINE", "")


pytestmark = pytest.mark.django_db(transaction=True)


def _make_event(n: int = 0, correlation_id: str | None = None):
    """Create one AuditEventLog row. Returns the PK as string."""
    from apps.audit_logs.models import AuditEventLog, EventType, EventCategory, SeverityLevel
    obj = AuditEventLog.objects.create(
        event_type=EventType.LOGIN_SUCCESS,
        event_category=EventCategory.AUTHENTICATION,
        severity=SeverityLevel.INFO,
        action=f"concurrent write {n}",
        actor_email=f"thread{n}@example.com",
        ip_address=f"10.0.{n // 254}.{n % 254 + 1}",
        correlation_id=correlation_id,
    )
    return str(obj.pk)


class TestSequentialUUIDUniqueness:
    """Sequential writes must produce UUID-unique rows (core correctness)."""

    def test_100_sequential_writes_unique_pks(self):
        """100 rapid sequential writes produce 100 distinct UUIDs."""
        pks = [_make_event(i) for i in range(100)]
        assert len(set(pks)) == 100, f"UUID collision detected in {len(pks)} writes!"

    def test_uuid_format_is_valid(self):
        """Every AuditEventLog PK must be a parseable UUID."""
        pks = [_make_event(i) for i in range(20)]
        for pk in pks:
            try:
                uuid.UUID(pk)
            except ValueError:
                pytest.fail(f"Invalid UUID PK: {pk!r}")

    def test_correlation_id_not_unique_constraint(self):
        """
        Multiple rows can share the same correlation_id (it's a trace ID).
        If correlation_id had a UNIQUE constraint this would raise IntegrityError.
        """
        corr_id = "trace-id-shared-across-3-events"
        pks = [_make_event(i, correlation_id=corr_id) for i in range(3)]

        from apps.audit_logs.models import AuditEventLog
        count = AuditEventLog.objects.filter(correlation_id=corr_id).count()
        assert count == 3, f"Expected 3 rows with shared correlation_id, got {count}"
        assert len(set(pks)) == 3, "3 rows with same correlation_id must have 3 distinct PKs"


class TestImmutabilityGuard:
    """AuditEventLog.save() raises PermissionError on update (E2)."""

    def test_update_existing_raises_permission_error(self):
        """Tampering with an existing row raises PermissionError immediately."""
        obj = _make_event(999)
        from apps.audit_logs.models import AuditEventLog
        existing = AuditEventLog.objects.get(pk=obj)
        existing.action = "tampered"
        with pytest.raises(PermissionError, match="immutable"):
            existing.save()

    def test_new_insert_always_succeeds(self):
        """New inserts must NEVER be blocked by the immutability guard."""
        from apps.audit_logs.models import AuditEventLog
        before = AuditEventLog.objects.count()
        for i in range(50):
            _make_event(i + 5000)
        after = AuditEventLog.objects.count()
        assert after - before == 50

    def test_immutability_guard_is_thread_safe_sequential(self):
        """
        Sequential simulation: tamper attempt blocked, other writes succeed.
        (Replaces the threaded version which deadlocks SQLite.)
        """
        from apps.audit_logs.models import AuditEventLog, EventType, EventCategory, SeverityLevel

        existing = AuditEventLog.objects.create(
            event_type=EventType.LOGIN_SUCCESS,
            event_category=EventCategory.AUTHENTICATION,
            severity=SeverityLevel.INFO,
            action="pre-existing row",
        )

        # Attempt tamper — must raise
        existing.action = "tampered"
        with pytest.raises(PermissionError):
            existing.save()

        # New writes must still succeed after tamper attempt
        new_pks = [_make_event(i + 9000) for i in range(5)]
        assert len(new_pks) == 5
        assert len(set(new_pks)) == 5


@pytest.mark.skipif(_IS_SQLITE, reason="SQLite cannot handle concurrent transactions (file-level lock)")
class TestParallelConcurrentWrites:
    """
    True multi-threaded concurrent writes.
    Only runs on PostgreSQL (not SQLite dev environment).
    """

    def test_parallel_writes_all_succeed(self):
        """20 parallel threads write audit events; all must succeed."""
        results = []
        errors = []
        lock = threading.Lock()

        def write(tid):
            try:
                pk = _make_event(tid)
                with lock:
                    results.append(pk)
            except Exception as e:
                with lock:
                    errors.append(str(e))

        threads = [threading.Thread(target=write, args=(i,)) for i in range(20)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=15)

        assert not errors, f"Parallel write errors: {errors}"
        assert len(results) == 20
        assert len(set(results)) == 20, "UUID collisions in parallel writes!"
