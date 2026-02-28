# apps/common/management/commands/seed_model_analytics.py
"""
Management command: seed_model_analytics

Scans ALL concrete models from INSTALLED_APPS and bootstraps (or
corrects) the ModelAnalytics table with real live DB counts.

Features:
  - Works for BOTH new-style (SoftDeleteModel) and legacy models.
  - Legacy models that don't have is_deleted = silently treated as
    all-active (total_soft_deleted = 0).
  - Safe to run repeatedly (idempotent — uses update_or_create).
  - Preserves existing total_updated and total_hard_deleted counters
    so historical data is not wiped on re-seed.
  - Runs automatically via post_migrate signal if the table is empty.

Usage:
  python manage.py seed_model_analytics
  python manage.py seed_model_analytics --reset   # Reset all counters

Performance note:
  Uses direct COUNT() SQL queries — extremely fast even with millions
  of rows. No Python-level iteration over model instances.
"""

import logging

from django.apps import apps as django_apps
from django.core.management.base import BaseCommand
from django.db import ProgrammingError, OperationalError


logger = logging.getLogger('application')

# ── Models we skip (same as signals.py) ──────────────────────────────
_EXCLUDED_MODEL_NAMES = frozenset({
    'Session', 'ContentType', 'Permission', 'LogEntry',
    'BlacklistedToken', 'OutstandingToken',
    'ModelAnalytics', 'DeletionAuditCounter', 'DeletedRecords',
    'CrontabSchedule', 'IntervalSchedule', 'PeriodicTask',
    'SolarSchedule', 'ClockedSchedule',
})

_EXCLUDED_APP_LABELS = frozenset({
    'admin',
    'contenttypes',
    'sessions',
    'django_celery_beat',
    'auditlog',
})


def _is_soft_delete_model(model):
    """Return True if the model inherits from SoftDeleteModel."""
    try:
        from apps.common.models import SoftDeleteModel
        return issubclass(model, SoftDeleteModel)
    except Exception:
        return False


def _should_seed(model):
    """Return True if this model should have an analytics row."""
    meta = getattr(model, '_meta', None)
    if meta is None:
        return False
    # Skip abstract models — they have no DB table
    if meta.abstract:
        return False
    # Skip proxy models (no independent table)
    if meta.proxy:
        return False
    # Skip excluded app labels
    if meta.app_label in _EXCLUDED_APP_LABELS:
        return False
    # Skip excluded model names
    if meta.object_name in _EXCLUDED_MODEL_NAMES:
        return False
    return True


def _count_for_model(model):
    """
    Return (total_active, total_soft_deleted) counts.

    Handles both SoftDeleteModel subclasses and legacy models
    that have no is_deleted field.
    """
    try:
        if _is_soft_delete_model(model):
            # Use the unrestricted manager for accurate counts
            if hasattr(model.objects, 'all_with_deleted'):
                qs_all = model.objects.all_with_deleted()
            else:
                qs_all = model._default_manager.all()

            total_active = qs_all.filter(is_deleted=False).count()
            total_soft   = qs_all.filter(is_deleted=True).count()
        else:
            # Legacy / third-party model: count all rows as active
            total_active = model._default_manager.all().count()
            total_soft   = 0

        return total_active, total_soft

    except (ProgrammingError, OperationalError) as exc:
        # Table might not exist yet (e.g., during initial migrations)
        logger.debug(
            "seed_model_analytics: skipping %s — DB error: %s",
            model.__name__, exc,
        )
        return None, None
    except Exception as exc:
        logger.warning(
            "seed_model_analytics: unexpected error for %s: %s",
            model.__name__, exc,
        )
        return None, None


class Command(BaseCommand):
    help = (
        "Seed (or re-seed) ModelAnalytics with real DB counts for "
        "every concrete model in INSTALLED_APPS. Safe to run "
        "multiple times — preserves existing total_updated and "
        "total_hard_deleted counters."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            '--reset',
            action='store_true',
            default=False,
            help=(
                'Reset ALL counters (including total_updated / '
                'total_hard_deleted). Use with caution.'
            ),
        )
        parser.add_argument(
            '--dry-run',
            action='store_true',
            default=False,
            help='Print what would be done without writing anything.',
        )
        parser.add_argument(
            '--app',
            type=str,
            default=None,
            help='Limit seeding to a specific app label.',
        )

    def handle(self, *args, **options):
        from apps.common.models import ModelAnalytics

        is_reset   = options['reset']
        is_dry_run = options['dry_run']
        app_filter = options.get('app')

        self.stdout.write(self.style.MIGRATE_HEADING(
            '\n📊  Seeding ModelAnalytics table...\n'
        ))

        all_models = [
            m for m in django_apps.get_models()
            if _should_seed(m)
        ]

        if app_filter:
            all_models = [
                m for m in all_models
                if m._meta.app_label == app_filter
            ]

        created_count = 0
        updated_count = 0
        skipped_count = 0

        for model in all_models:
            model_name = model._meta.object_name
            app_label  = model._meta.app_label

            total_active, total_soft = _count_for_model(model)
            if total_active is None:
                skipped_count += 1
                continue

            total_records = total_active + total_soft
            total_lifetime = total_records  # best we can do for existing data

            if is_dry_run:
                self.stdout.write(
                    f'  [DRY-RUN] {app_label}.{model_name}: '
                    f'active={total_active} soft={total_soft} '
                    f'total={total_records}'
                )
                continue

            # Preserve existing total_updated / total_hard_deleted
            # unless --reset was passed.
            existing = ModelAnalytics.objects.filter(
                model_name=model_name
            ).values('total_updated', 'total_hard_deleted', 'total_lifetime_records').first()

            if existing and not is_reset:
                # Keep the historical counters; only refresh live counts.
                # If we already have a total_lifetime_records value that's
                # higher (because records were hard-deleted), preserve it.
                total_lifetime = max(
                    total_lifetime,
                    existing.get('total_lifetime_records', 0),
                )
                _, is_new = ModelAnalytics.objects.update_or_create(
                    model_name=model_name,
                    defaults={
                        'app_label': app_label,
                        'total_active': total_active,
                        'total_soft_deleted': total_soft,
                        'total_records': total_records,
                        'total_lifetime_records': total_lifetime,
                        # Preserve historical totals
                        'total_hard_deleted': existing.get('total_hard_deleted', 0),
                        'total_updated': existing.get('total_updated', 0),
                        # Re-compute total_created as best we can
                        'total_created': (
                            total_records
                            + existing.get('total_hard_deleted', 0)
                        ),
                    },
                )
            else:
                # Full reset or new row
                _, is_new = ModelAnalytics.objects.update_or_create(
                    model_name=model_name,
                    defaults={
                        'app_label': app_label,
                        'total_active': total_active,
                        'total_soft_deleted': total_soft,
                        'total_records': total_records,
                        'total_lifetime_records': total_lifetime,
                        'total_created': total_records,
                        'total_hard_deleted': 0,
                        'total_updated': 0,
                    },
                )

            if is_new:
                created_count += 1
                self.stdout.write(
                    f'  ✅ NEW  {app_label}.{model_name}: '
                    f'active={total_active} soft={total_soft}'
                )
            else:
                updated_count += 1
                self.stdout.write(
                    f'  🔄 UPD  {app_label}.{model_name}: '
                    f'active={total_active} soft={total_soft}'
                )

        # Summary
        self.stdout.write('')
        self.stdout.write(self.style.SUCCESS(
            f'✔  Done. Created: {created_count} | '
            f'Updated: {updated_count} | '
            f'Skipped: {skipped_count} | '
            f'Total: {len(all_models)}'
        ))
