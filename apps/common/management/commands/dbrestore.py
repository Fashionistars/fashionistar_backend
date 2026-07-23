# apps/common/management/commands/dbrestore.py
"""
Django management command for database restoration.

Usage:
  # List available backups
  python manage.py dbrestore --list

  # Verify a backup (no changes to DB)
  python manage.py dbrestore --verify rolling/latest.sql.gz

  # Auto-restore (best method for current environment)
  python manage.py dbrestore --from rolling/latest.sql.gz

  # Restore with specific method
  python manage.py dbrestore --from rolling/latest.sql.gz --method psql
  python manage.py dbrestore --from rolling/latest.sql.gz --method psycopg
  python manage.py dbrestore --from rolling/latest.sql.gz --method orm
  python manage.py dbrestore --from rolling/latest.sql.gz --method merge

  # Non-destructive merge (preserve existing data)
  python manage.py dbrestore --from hourly/20240115_100000.sql.gz --merge

  # Restore to a different database URL
  python manage.py dbrestore --from rolling/latest.sql.gz --db-url "postgresql://..."
"""

import sys
import json
import logging

from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from apps.common.tasks.dbrestore import (
    _restore_backup,
    _detect_target_engine,
)
from apps.common.tasks.dbbackups import _list_storage_files, _parse_timestamp_from_filename

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Restore database from a backup file in the configured storage backend"

    def add_arguments(self, parser):
        parser.add_argument(
            "--list",
            action="store_true",
            dest="list",
            default=False,
            help="List all available backups in storage",
        )
        parser.add_argument(
            "--from",
            dest="storage_path",
            type=str,
            default=None,
            help="Storage path of the backup file (e.g., rolling/latest.sql.gz)",
        )
        parser.add_argument(
            "--verify",
            dest="verify_path",
            type=str,
            default=None,
            help="Verify a backup file without restoring (no DB changes)",
        )
        parser.add_argument(
            "--method",
            dest="method",
            type=str,
            default="auto",
            choices=["auto", "psql", "psycopg", "orm", "merge"],
            help="Restore method: auto (default), psql, psycopg, orm, or merge",
        )
        parser.add_argument(
            "--merge",
            action="store_true",
            dest="merge_mode",
            default=False,
            help="Non-destructive merge mode (preserve existing data in target DB)",
        )
        parser.add_argument(
            "--db-url",
            dest="db_url",
            type=str,
            default=None,
            help="Override target database URL (defaults to DATABASE_URL env var)",
        )
        parser.add_argument(
            "--json",
            action="store_true",
            dest="json_output",
            default=False,
            help="Output results as JSON (for scripting/automation)",
        )

    def handle(self, *args, **options):
        list_mode = options["list"]
        storage_path = options["storage_path"]
        verify_path = options["verify_path"]
        method = options["method"]
        merge_mode = options["merge_mode"]
        db_url = options["db_url"]
        json_output = options["json_output"]

        # --- LIST MODE ---
        if list_mode:
            self._list_backups(json_output)
            return

        # --- VERIFY MODE ---
        if verify_path:
            self._verify_backup(verify_path, json_output)
            return

        # --- RESTORE MODE ---
        if not storage_path:
            raise CommandError("Either --from, --list, or --verify is required")

        # Show target DB info
        engine = _detect_target_engine()
        db_name = connection.settings_dict.get("NAME", "unknown")

        if not json_output:
            self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
            self.stdout.write(self.style.MIGRATE_HEADING("  FASHIONISTAR Database Restoration"))
            self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
            self.stdout.write(f"  Backup file : {storage_path}")
            self.stdout.write(f"  Method      : {method}")
            self.stdout.write(f"  Merge mode  : {merge_mode}")
            self.stdout.write(f"  Target DB   : {engine} ({db_name})")
            self.stdout.write(self.style.MIGRATE_HEADING("-" * 70))
            self.stdout.write("  WARNING: This will modify the target database!")
            if not merge_mode and method != "merge":
                self.stdout.write(self.style.WARNING("  DESTRUCTIVE mode: existing data may be overwritten!"))
            self.stdout.write(self.style.MIGRATE_HEADING("-" * 70))

            # Confirmation prompt (skip in JSON mode)
            try:
                response = input("  Continue? [y/N]: ").strip().lower()
                if response != "y":
                    self.stdout.write(self.style.WARNING("  Cancelled."))
                    return
            except (EOFError, KeyboardInterrupt):
                self.stdout.write(self.style.WARNING("\n  Cancelled."))
                return

            self.stdout.write("")

        # Execute restore
        result = _restore_backup(
            storage_path=storage_path,
            method=method,
            merge_mode=merge_mode,
            target_db_url=db_url,
        )

        if json_output:
            self.stdout.write(json.dumps(result, indent=2, default=str))
        else:
            self._print_result(result)

    def _list_backups(self, json_output):
        """List all available backups in storage."""
        tiers = ("rolling", "hourly", "monthly")
        all_backups = {}

        for tier in tiers:
            files = _list_storage_files(tier)
            all_backups[tier] = []
            for fname, fpath in files:
                ts = _parse_timestamp_from_filename(fname)
                all_backups[tier].append({
                    "filename": fname,
                    "path": fpath,
                    "timestamp": ts.isoformat() if ts else None,
                })

        if json_output:
            self.stdout.write(json.dumps(all_backups, indent=2, default=str))
        else:
            self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
            self.stdout.write(self.style.MIGRATE_HEADING("  Available Backups"))
            self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))

            for tier in tiers:
                backups = all_backups[tier]
                self.stdout.write(f"\n  [{tier.upper()}] ({len(backups)} file(s))")
                if not backups:
                    self.stdout.write("    (none)")
                for b in backups:
                    ts_str = b["timestamp"][:19].replace("T", " ") if b["timestamp"] else "unknown"
                    self.stdout.write(f"    {b['path']:<50s}  {ts_str}")

            self.stdout.write("")
            total = sum(len(all_backups[t]) for t in tiers)
            self.stdout.write(f"  Total: {total} backup file(s)")
            self.stdout.write("")

    def _verify_backup(self, verify_path, json_output):
        """Verify a backup without restoring."""
        from apps.common.tasks.dbrestore import _download_from_storage, _detect_backup_format, _parse_copy_blocks, _cleanup_temp

        try:
            sql_file, tmp_dir = _download_from_storage(verify_path)

            try:
                with open(sql_file, "r", encoding="utf-8", errors="replace") as f:
                    sql_content = f.read()

                backup_format = _detect_backup_format(sql_content)
                blocks = _parse_copy_blocks(sql_content)
                total_rows = sum(b["row_count"] for b in blocks)

                result = {
                    "status": "ok",
                    "storage_path": verify_path,
                    "backup_format": backup_format,
                    "tables_found": len(blocks),
                    "estimated_rows": total_rows,
                    "file_size_kb": round(len(sql_content) / 1024, 2),
                    "table_names": [b["table_name"] for b in blocks[:50]],
                }

                if json_output:
                    self.stdout.write(json.dumps(result, indent=2, default=str))
                else:
                    self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
                    self.stdout.write(self.style.MIGRATE_HEADING("  Backup Verification"))
                    self.stdout.write(self.style.MIGRATE_HEADING("=" * 70))
                    self.stdout.write(f"  File        : {verify_path}")
                    self.stdout.write(f"  Format      : {backup_format}")
                    self.stdout.write(f"  Size        : {result['file_size_kb']:.2f} KB")
                    self.stdout.write(f"  Tables      : {len(blocks)}")
                    self.stdout.write(f"  Est. rows   : {total_rows}")
                    self.stdout.write(self.style.MIGRATE_HEADING("-" * 70))
                    self.stdout.write("  Tables found:")
                    for b in blocks[:20]:
                        self.stdout.write(f"    {b['table_name']:<40s}  ~{b['row_count']} rows")
                    if len(blocks) > 20:
                        self.stdout.write(f"    ... and {len(blocks) - 20} more")
                    self.stdout.write("")

            finally:
                _cleanup_temp(tmp_dir)

        except Exception as exc:
            if json_output:
                self.stdout.write(json.dumps({"status": "error", "error": str(exc)}, indent=2))
            else:
                self.stdout.write(self.style.ERROR(f"  Verification failed: {exc}"))

    def _print_result(self, result):
        """Print restore result in human-readable format."""
        status = result.get("status", "unknown")

        self.stdout.write(self.style.MIGRATE_HEADING("-" * 70))

        if status == "ok":
            self.stdout.write(self.style.SUCCESS(f"  RESTORE COMPLETED ({result.get('method', 'unknown')})"))
        else:
            self.stdout.write(self.style.ERROR(f"  RESTORE FAILED: {result.get('error', 'unknown error')}"))

        self.stdout.write(self.style.MIGRATE_HEADING("-" * 70))

        # Print key metrics
        for key in ("method", "backup_format", "target_engine", "merge_mode",
                     "tables_total", "tables_restored", "tables_merged",
                     "tables_skipped", "rows_inserted", "total_rows",
                     "duration_seconds"):
            if key in result:
                label = key.replace("_", " ").title()
                self.stdout.write(f"  {label:<20s}: {result[key]}")

        # Print errors if any
        errors = result.get("errors", [])
        if errors:
            self.stdout.write(self.style.WARNING(f"\n  Errors ({len(errors)}):"))
            for err in errors[:10]:
                self.stdout.write(self.style.WARNING(f"    - {err}"))
            if len(errors) > 10:
                self.stdout.write(self.style.WARNING(f"    ... and {len(errors) - 10} more"))

        warnings = result.get("warnings")
        if warnings:
            self.stdout.write(self.style.WARNING(f"\n  Warnings: {warnings[:200]}"))

        self.stdout.write("")
