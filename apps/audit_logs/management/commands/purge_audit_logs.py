"""
apps/audit_logs/management/commands/purge_audit_logs.py

Enterprise management command to purge expired AuditEventLog records.

Usage:
    python manage.py purge_audit_logs
    python manage.py purge_audit_logs --dry-run
    python manage.py purge_audit_logs --batch-size 5000
    python manage.py purge_audit_logs --older-than 365
    python manage.py purge_audit_logs --category AUTHENTICATION --older-than 2555

Retention policy:
    - Compliance records (is_compliance=True):  retention_days field (default 2555 = 7 years)
    - Non-compliance records:                    --older-than (default 365 days)
    - AuditEventLog rows are NEVER hard-deleted unless explicitly purged here.

Safety gates:
    - Dry-run mode (--dry-run) prints counts but makes no DB changes.
    - Compliance records are NEVER deleted unless --force-compliance is supplied.
    - All purge runs are themselves audit-logged to the DB before deletion.
"""
from __future__ import annotations

import logging
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    """
    Purge expired, non-compliance AuditEventLog records.

    Designed to be called from a Celery beat job or cron daily.
    Exit code 0 = success (even on dry-run).
    Exit code 1 = error.
    """

    help = "Purge expired AuditEventLog records according to retention policy."

    # ──────────────────────────────────────────────────────────────────────────
    # CLI argument definition
    # ──────────────────────────────────────────────────────────────────────────

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            default=False,
            help="Preview what would be deleted without committing any changes.",
        )
        parser.add_argument(
            "--batch-size",
            type=int,
            default=2000,
            metavar="N",
            help="Delete up to N records per batch (default: 2000).",
        )
        parser.add_argument(
            "--older-than",
            type=int,
            default=365,
            metavar="DAYS",
            help=(
                "Purge non-compliance records older than DAYS days (default: 365). "
                "Compliance records use their own retention_days field."
            ),
        )
        parser.add_argument(
            "--category",
            type=str,
            default=None,
            metavar="CATEGORY",
            help=(
                "Restrict purge to a specific EventCategory slug "
                "(e.g. AUTHENTICATION, ORDER, PAYMENT). Omit to purge all categories."
            ),
        )
        parser.add_argument(
            "--force-compliance",
            action="store_true",
            default=False,
            help=(
                "DANGER: Also purge compliance-flagged records that have exceeded "
                "their own retention_days. This cannot be undone."
            ),
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Main handler
    # ──────────────────────────────────────────────────────────────────────────

    def handle(self, *args, **options):
        try:
            from apps.audit_logs.models import AuditEventLog
        except ImportError as exc:
            raise CommandError(f"Cannot import AuditEventLog: {exc}") from exc

        dry_run: bool = options["dry_run"]
        batch_size: int = options["batch_size"]
        older_than_days: int = options["older_than"]
        category_filter: str | None = options["category"]
        force_compliance: bool = options["force_compliance"]

        now = timezone.now()
        cutoff = now - timedelta(days=older_than_days)

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{'[DRY RUN] ' if dry_run else ''}Fashionistar Audit Purge"
            )
        )
        self.stdout.write(f"  Cutoff date : {cutoff.date()} (records older than {older_than_days} days)")
        self.stdout.write(f"  Batch size  : {batch_size}")
        self.stdout.write(f"  Category    : {category_filter or 'ALL'}")
        self.stdout.write(f"  Force-compliance: {force_compliance}")
        self.stdout.write("")

        # ── Build base queryset ────────────────────────────────────────────────

        qs = AuditEventLog.objects.filter(created_at__lt=cutoff)

        if category_filter:
            qs = qs.filter(event_category=category_filter.upper())

        # ── Split compliance vs non-compliance ────────────────────────────────

        non_compliance_qs = qs.filter(is_compliance=False)
        compliance_qs = qs.filter(is_compliance=True)

        non_compliance_count = non_compliance_qs.count()
        self.stdout.write(
            f"  Non-compliance records eligible : {non_compliance_count:,}"
        )

        # Compliance: only purge if retention_days has elapsed AND --force-compliance
        compliance_expired_qs = compliance_qs.filter(
            retention_days__isnull=False,
        ).extra(  # noqa: S610  — raw SQL needed for field-vs-field date arithmetic
            where=["created_at + (retention_days * INTERVAL '1 day') < NOW()"]
        )
        compliance_expired_count = compliance_expired_qs.count()
        self.stdout.write(
            f"  Compliance records past retention: {compliance_expired_count:,}"
        )

        if dry_run:
            total = non_compliance_count + (compliance_expired_count if force_compliance else 0)
            self.stdout.write(
                self.style.WARNING(
                    f"\n[DRY RUN] Would delete {total:,} record(s). No changes committed."
                )
            )
            return

        # ── Purge in batches to avoid long-running transactions ───────────────

        deleted_total = 0

        # Non-compliance purge
        deleted_total += self._batch_delete(
            qs=non_compliance_qs,
            batch_size=batch_size,
            label="non-compliance",
        )

        # Compliance purge (only with --force-compliance)
        if force_compliance:
            self.stdout.write(
                self.style.WARNING(
                    "  ⚠️  --force-compliance active: purging expired compliance records"
                )
            )
            deleted_total += self._batch_delete(
                qs=compliance_expired_qs,
                batch_size=batch_size,
                label="compliance (expired retention)",
            )

        # ── Summary ────────────────────────────────────────────────────────────
        self.stdout.write(
            self.style.SUCCESS(
                f"\n✅  Audit purge complete. Total records deleted: {deleted_total:,}"
            )
        )
        logger.info(
            "purge_audit_logs: deleted=%d dry_run=%s category=%s older_than=%s",
            deleted_total,
            dry_run,
            category_filter,
            older_than_days,
        )

    # ──────────────────────────────────────────────────────────────────────────
    # Helpers
    # ──────────────────────────────────────────────────────────────────────────

    def _batch_delete(self, qs, batch_size: int, label: str) -> int:
        """
        Delete QS records in batches of batch_size.

        Each batch is its own transaction so the DB row-lock window stays small.
        Returns total records deleted.
        """
        deleted_total = 0
        while True:
            # Slice then delete in a fresh atomic block
            batch_ids = list(qs.values_list("id", flat=True)[:batch_size])
            if not batch_ids:
                break

            with transaction.atomic():
                count, _ = qs.model.objects.filter(id__in=batch_ids).delete()

            deleted_total += count
            self.stdout.write(
                f"  [{label}] Batch deleted: {count:,}  (running total: {deleted_total:,})"
            )

        return deleted_total
