"""
Management command: reconcile_registry

Backfills missing rows in UserLifecycleRegistry for any UnifiedUser
that doesn't already have a registry entry.

Also removes ghost rows (rows whose user_uuid does NOT match any
existing UnifiedUser) created by stress tests or migration artefacts.

Usage:
    uv run manage.py reconcile_registry              # dry-run (preview only)
    uv run manage.py reconcile_registry --commit     # apply changes
    uv run manage.py reconcile_registry --purge-ghosts --commit
"""

from django.core.management.base import BaseCommand
from django.db import transaction


class Command(BaseCommand):
    help = (
        "Backfill missing UserLifecycleRegistry rows and "
        "optionally purge ghost rows created by stress tests."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--commit",
            action="store_true",
            default=False,
            help="Actually apply changes (default is dry-run / preview only).",
        )
        parser.add_argument(
            "--purge-ghosts",
            action="store_true",
            default=False,
            help=(
                "Also delete UserLifecycleRegistry rows whose user_uuid "
                "does NOT exist in UnifiedUser (phantom stress-test rows)."
            ),
        )

    def handle(self, *args, **options):
        from apps.common.models import UserLifecycleRegistry
        from apps.authentication.models import UnifiedUser

        commit = options["commit"]
        purge_ghosts = options["purge_ghosts"]
        dry_run_tag = "" if commit else "[DRY-RUN] "

        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{'='*60}\n"
                f"  UserLifecycleRegistry Reconciler\n"
                f"  Mode: {'COMMIT' if commit else 'DRY-RUN (use --commit to apply)'}\n"
                f"{'='*60}\n"
            )
        )

        # ── Phase 1: Count state ──────────────────────────────────────
        total_users = UnifiedUser.objects.using("default").count()
        total_registry = UserLifecycleRegistry.objects.count()

        self.stdout.write(
            f"UnifiedUser rows        : {total_users}\n"
            f"UserLifecycleRegistry   : {total_registry}\n"
        )

        # ── Phase 2: Find missing (users without registry rows) ───────
        existing_uuids = frozenset(
            UserLifecycleRegistry.objects
            .values_list("user_uuid", flat=True)
        )
        all_users = (
            UnifiedUser.objects
            .using("default")
            .values_list(
                "id", "email", "phone", "member_id",
                "role", "auth_provider", "country",
                "state", "city", "is_deleted",
            )
        )

        missing = []
        for (uid, email, phone, member_id,
             role, auth_provider, country, state, city, is_deleted) in all_users:
            if uid not in existing_uuids:
                missing.append({
                    "user_uuid": uid,
                    "email": email,
                    "phone": str(phone) if phone else None,
                    "member_id": member_id or "",
                    "role": role or "",
                    "auth_provider": auth_provider or "email",
                    "country": country,
                    "state": state,
                    "city": city,
                    "status": (
                        UserLifecycleRegistry.STATUS_SOFT_DELETED
                        if is_deleted else
                        UserLifecycleRegistry.STATUS_ACTIVE
                    ),
                })

        self.stdout.write(
            f"\nMissing registry rows   : {len(missing)}"
        )

        if missing:
            self.stdout.write(self.style.WARNING(
                f"{dry_run_tag}Will create {len(missing)} registry row(s):"
            ))
            for m in missing[:10]:  # show first 10
                self.stdout.write(f"  → {m['email'] or m['phone']} [{m['user_uuid']}]")
            if len(missing) > 10:
                self.stdout.write(f"  … and {len(missing) - 10} more")

            if commit:
                with transaction.atomic():
                    created = 0
                    for m in missing:
                        _, was_created = UserLifecycleRegistry.objects.get_or_create(
                            user_uuid=m["user_uuid"],
                            defaults={
                                k: v for k, v in m.items()
                                if k != "user_uuid"
                            },
                        )
                        if was_created:
                            created += 1
                self.stdout.write(self.style.SUCCESS(
                    f"✅ Created {created} missing registry row(s)."
                ))
        else:
            self.stdout.write(self.style.SUCCESS("✅ No missing rows — registry is complete."))

        # ── Phase 3: Purge ghost rows ─────────────────────────────────
        if purge_ghosts:
            # Rows in registry that have NO corresponding UnifiedUser
            real_user_uuids = frozenset(
                UnifiedUser.objects
                .using("default")
                .values_list("id", flat=True)
            )
            ghosts = UserLifecycleRegistry.objects.exclude(
                user_uuid__in=real_user_uuids
            )
            ghost_count = ghosts.count()

            self.stdout.write(
                f"\nGhost rows (no matching UnifiedUser): {ghost_count}"
            )

            if ghost_count > 0:
                self.stdout.write(self.style.WARNING(
                    f"{dry_run_tag}Will DELETE {ghost_count} ghost row(s):"
                ))
                for g in ghosts.values("user_uuid", "email", "member_id")[:10]:
                    self.stdout.write(
                        f"  ✗ {g['email']} [{g['user_uuid']}] "
                        f"member_id={g['member_id']}"
                    )
                if ghost_count > 10:
                    self.stdout.write(f"  … and {ghost_count - 10} more")

                if commit:
                    deleted, _ = ghosts.delete()
                    self.stdout.write(self.style.SUCCESS(
                        f"✅ Deleted {deleted} ghost registry row(s)."
                    ))
            else:
                self.stdout.write(self.style.SUCCESS("✅ No ghost rows found."))

        # ── Final summary ─────────────────────────────────────────────
        final_count = UserLifecycleRegistry.objects.count()
        self.stdout.write(
            self.style.MIGRATE_HEADING(
                f"\n{'='*60}\n"
                f"  Final count: {final_count} registry row(s)\n"
                f"  Expected   : {total_users} (matching UnifiedUser)\n"
                f"{'='*60}\n"
            )
        )
        if not commit:
            self.stdout.write(self.style.NOTICE(
                "ℹ️  This was a DRY-RUN. No changes were made. "
                "Run with --commit to apply."
            ))
