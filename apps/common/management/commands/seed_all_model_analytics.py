"""
Management command: seed_all_model_analytics

Scans every installed Django model, counts its current DB rows,
and calls ModelAnalytics.record_seeded() to populate/correct
the analytics counters.

Idempotent: safe to run multiple times. Each run overwrites
counters with the live DB counts (corrects any drift).

Usage:
    uv run manage.py seed_all_model_analytics        # dry-run (preview)
    uv run manage.py seed_all_model_analytics --commit
    uv run manage.py seed_all_model_analytics --app authentication
"""

from django.core.management.base import BaseCommand


# Models we deliberately skip (mirrors signals.py exclusions)
_EXCLUDED_MODEL_NAMES = frozenset({
    "Session", "ContentType", "Permission", "LogEntry",
    "BlacklistedToken", "OutstandingToken",
    "ModelAnalytics", "DeletionAuditCounter", "DeletedRecords",
    "CrontabSchedule", "IntervalSchedule", "PeriodicTask",
    "SolarSchedule", "ClockedSchedule", "MemberIDCounter",
})
_EXCLUDED_APP_LABELS = frozenset({
    "admin", "auth", "contenttypes", "sessions",
    "django_celery_beat", "auditlog",
})


class Command(BaseCommand):
    help = (
        "Seed or correct ModelAnalytics counters from live DB counts. "
        "Idempotent — safe to run multiple times."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            default=False,
            help="Apply changes (default is dry-run / preview only).",
        )
        parser.add_argument(
            "--app",
            type=str,
            default=None,
            help="Limit to a single app label (e.g. 'authentication').",
        )

    def handle(self, *args, **options):
        from django.apps import apps as django_apps
        from apps.common.models import ModelAnalytics

        commit = options["commit"]
        filter_app = options.get("app")
        dry_run_tag = "" if commit else "[DRY-RUN] "

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{'='*60}\n"
                f"  ModelAnalytics Seeder\n"
                f"  Mode: {'COMMIT' if commit else 'DRY-RUN (use --commit to apply)'}\n"
                f"{'='*60}\n"
            )
        )

        processed = 0
        skipped = 0
        rows_updated = 0

        all_models = django_apps.get_models(include_auto_created=False)

        for model in all_models:
            meta = model._meta
            app_label = meta.app_label
            model_name = meta.object_name

            # Apply filter
            if filter_app and app_label != filter_app:
                continue

            if app_label in _EXCLUDED_APP_LABELS:
                skipped += 1
                continue
            if model_name in _EXCLUDED_MODEL_NAMES:
                skipped += 1
                continue
            if meta.abstract or meta.proxy:
                skipped += 1
                continue

            # Count live rows
            try:
                has_soft_delete = hasattr(model, "is_deleted") and hasattr(
                    model.objects, "all_with_deleted"
                )

                if has_soft_delete:
                    all_qs = model.objects.all_with_deleted()
                    total_active = all_qs.filter(is_deleted=False).count()
                    total_soft = all_qs.filter(is_deleted=True).count()
                else:
                    total_active = model.objects.count()
                    total_soft = 0

                total_created = total_active + total_soft

                self.stdout.write(
                    f"{dry_run_tag}{app_label}.{model_name}: "
                    f"active={total_active} soft_deleted={total_soft} "
                    f"total_created={total_created}"
                )

                if commit:
                    ModelAnalytics.record_seeded(
                        model_name=model_name,
                        app_label=app_label,
                        total_active=total_active,
                        total_soft_deleted=total_soft,
                        total_created=total_created,
                    )
                    rows_updated += 1
                processed += 1

            except Exception as exc:
                self.stdout.write(self.style.ERROR(
                    f"  ✗ Error counting {model_name}: {exc}"
                ))
                skipped += 1

        # ── Summary ───────────────────────────────────────────────────
        total_analytics = ModelAnalytics.objects.count() if commit else "N/A (dry-run)"
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{'='*60}\n"
                f"  Processed : {processed} model(s)\n"
                f"  Skipped   : {skipped} (internals/excluded)\n"
                f"  Updated   : {rows_updated} ModelAnalytics rows\n"
                f"  Total MA  : {total_analytics}\n"
                f"{'='*60}\n"
            )
        )
        if not commit:
            self.stdout.write(self.style.NOTICE(
                "ℹ️  DRY-RUN only. Use --commit to apply."
            ))
