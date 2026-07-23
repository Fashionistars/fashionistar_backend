# apps/common/tasks/dbbackups.py
"""
FASHIONISTAR - Automated Database Backup Tasks (Celery)
=========================================================

Three-tier backup strategy:
  1. Rolling  (every 5 min)  - single overwriting file: rolling/latest.sql.gz
  2. Hourly   (every 1 hour) - timestamped file: hourly/YYYYMMDD_HHMMSS.sql.gz
                                24 files/day, auto-deleted after 30 days
  3. Monthly  (1st of month)  - timestamped file: monthly/YYYYMM_01_HHMMSS.sql.gz
                                auto-deleted after 365 days (12 months)

Cleanup tasks:
  - cleanup_hourly_backups: deletes hourly backups older than 30 days (daily at 4 AM UTC)
  - cleanup_monthly_backups: deletes monthly backups older than 365 days (monthly on 2nd)

Storage:
  - Development: local filesystem (backups/rolling/, backups/hourly/, backups/monthly/)
  - Production:  Cloudinary (backups/rolling/, backups/hourly/, backups/monthly/)
  Both use Django's storage API, so the tasks are fully storage-agnostic.

All backups use gzip compression.
Backup-level encryption is supported via DBBACKUP_ENCRYPTION_KEY env var (Fernet symmetric encryption).
When DBBACKUP_ENCRYPTION_KEY is set, the pipeline becomes:
  pg_dump -> gzip -> Fernet encrypt -> upload to storage
When not set, the pipeline is:
  pg_dump -> gzip -> upload to storage
Backups are created via pg_dump subprocess for full fidelity (extensions, vectors, etc).
"""

import os
import subprocess
import tempfile
import gzip
import shutil
import logging
import re
from datetime import datetime, timedelta

from celery import shared_task
from django.conf import settings
from django.core.files.storage import default_storage

logger = logging.getLogger(__name__)


# === HELPERS ===

def _get_backup_folder():
    """Return the Cloudinary folder prefix or local backup root."""
    return getattr(settings, "DBBACKUP_CLOUDINARY_FOLDER", "backups")


def _get_storage():
    """Return the configured Django storage backend for backups.
    Uses STORAGES['dbbackups'] if configured, otherwise falls back to default_storage.
    This is important because default media storage (MediaCloudinaryStorage)
    rejects non-image files like .sql.gz backups.
    """
    storages = getattr(settings, "STORAGES", {})
    if "dbbackups" in storages:
        backend = storages["dbbackups"]["BACKEND"]
        options = storages["dbbackups"].get("OPTIONS", {})
        from django.utils.module_loading import import_string
        storage_cls = import_string(backend)
        return storage_cls(**options)
    return default_storage


def _get_database_url():
    """Extract DATABASE_URL from environment."""
    return os.environ.get("DATABASE_URL", "")


def _run_pg_dump(output_file):
    """
    Create a database backup at output_file (plain SQL).
    Tries pg_dump binary first (best fidelity for pgvector/extensions).
    Falls back to pure-Python psycopg dump if pg_dump not found.
    Returns True on success, False on failure.
    """
    db_url = _get_database_url()
    if not db_url:
        logger.error("[DBBACKUP] No DATABASE_URL found in environment")
        return False

    # --- Strategy 1: pg_dump binary ---
    cmd = [
        "pg_dump",
        db_url,
        "--no-owner",
        "--no-privileges",
        "--clean",
        "--if-exists",
        "--format=plain",
        f"--file={output_file}",
    ]

    logger.info("[DBBACKUP] Attempting pg_dump -> %s", output_file)

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode == 0:
            logger.info("[DBBACKUP] pg_dump completed successfully")
            return True
        logger.error("[DBBACKUP] pg_dump failed (exit %d): %s", result.returncode, result.stderr[:500])
    except FileNotFoundError:
        logger.warning("[DBBACKUP] pg_dump binary not found, falling back to psycopg dump")
    except subprocess.TimeoutExpired:
        logger.error("[DBBACKUP] pg_dump timed out after 300 seconds")
        return False
    except Exception as exc:
        logger.warning("[DBBACKUP] pg_dump error: %s, falling back to psycopg dump", exc)

    # --- Strategy 2: Pure-Python psycopg dump (no pg_dump binary needed) ---
    # Uses psycopg's COPY TO STDOUT to export each table's data.
    # Handles Neon serverless connection drops with per-table reconnection.
    logger.info("[DBBACKUP] Using pure-Python psycopg dump fallback")
    try:
        import psycopg
        from psycopg import sql

        def _get_connection():
            """Create a fresh autocommit connection to Neon."""
            c = psycopg.connect(db_url, connect_timeout=30)
            c.autocommit = True
            return c

        conn = _get_connection()

        with open(output_file, "w", encoding="utf-8", errors="replace") as f:
            f.write("-- FASHIONISTAR database backup (psycopg fallback)\n")
            f.write(f"-- Generated: {datetime.utcnow().isoformat()}Z\n")
            f.write("-- This is a data-only backup. Schema must be restored via migrations.\n\n")

            # Get all user tables (exclude playing_with_neon - Neon demo table)
            with conn.cursor() as cur:
                cur.execute("""
                    SELECT table_schema, table_name
                    FROM information_schema.tables
                    WHERE table_schema NOT IN ('pg_catalog', 'information_schema', 'pg_toast')
                      AND table_type = 'BASE TABLE'
                      AND table_name != 'playing_with_neon'
                    ORDER BY table_schema, table_name;
                """)
                tables = cur.fetchall()

            total_tables = len(tables)
            dumped = 0

            # Dump each table's data using COPY with reconnection on failure
            for schema, table in tables:
                fq_table = f'"{schema}"."{table}"'
                logger.info("[DBBACKUP] Dumping %s (%d/%d)", fq_table, dumped + 1, total_tables)

                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        f.write(f"\n-- Data for {fq_table}\n")
                        f.write(f"COPY {fq_table} FROM stdin;\n")
                        with conn.cursor() as cur:
                            with cur.copy(f"COPY {fq_table} TO STDOUT") as copy:
                                for row in copy:
                                    f.write(bytes(row).decode("utf-8", errors="replace"))
                        f.write("\\.\n")
                        f.flush()
                        dumped += 1
                        break
                    except (psycopg.OperationalError, psycopg.InterfaceError) as conn_err:
                        logger.warning(
                            "[DBBACKUP] Connection lost on %s (attempt %d/%d): %s",
                            fq_table, attempt + 1, max_retries, conn_err,
                        )
                        try:
                            conn.close()
                        except Exception:
                            pass
                        if attempt < max_retries - 1:
                            conn = _get_connection()
                        else:
                            logger.error("[DBBACKUP] Failed to dump %s after %d retries", fq_table, max_retries)
                            f.write(f"-- ERROR: Could not dump {fq_table} after {max_retries} retries\n")
                    except Exception as tbl_err:
                        logger.warning("[DBBACKUP] Error dumping %s: %s", fq_table, tbl_err)
                        f.write(f"-- ERROR dumping {fq_table}: {tbl_err}\n")
                        break

        try:
            conn.close()
        except Exception:
            pass

        logger.info("[DBBACKUP] psycopg dump completed: %d/%d tables dumped -> %s", dumped, total_tables, output_file)
        return True
    except Exception as exc:
        logger.error("[DBBACKUP] psycopg dump fallback failed: %s", exc)
        return False


def _gzip_file(source_path, dest_path):
    """Compress a file with gzip."""
    with open(source_path, "rb") as src:
        with gzip.open(dest_path, "wb", compresslevel=6) as dst:
            shutil.copyfileobj(src, dst)
    return os.path.getsize(dest_path)


def _is_encryption_enabled():
    """Check if backup encryption is enabled via DBBACKUP_ENCRYPTION_KEY env var."""
    return bool(os.environ.get("DBBACKUP_ENCRYPTION_KEY", "").strip())


def _encrypt_file(source_path, dest_path):
    """
    Encrypt a file using Fernet symmetric encryption.
    The entire file is read, encrypted, and written to dest_path.
    Used after gzip compression when DBBACKUP_ENCRYPTION_KEY is set.
    """
    from cryptography.fernet import Fernet

    key = os.environ.get("DBBACKUP_ENCRYPTION_KEY", "").strip()
    if not key:
        raise ValueError("DBBACKUP_ENCRYPTION_KEY not set but encryption requested")

    fernet = Fernet(key.encode() if isinstance(key, str) else key)

    with open(source_path, "rb") as f:
        plaintext = f.read()

    ciphertext = fernet.encrypt(plaintext)

    with open(dest_path, "wb") as f:
        f.write(ciphertext)

    return os.path.getsize(dest_path)


def _upload_to_storage(local_path, storage_path):
    """
    Upload a local file to the configured Django storage backend.
    Works with both FileSystemStorage (dev) and CloudinaryStorage (prod).
    """
    storage = _get_storage()
    with open(local_path, "rb") as f:
        saved_path = storage.save(storage_path, f)
    return saved_path


def _create_backup(tier, filename):
    """
    Full backup pipeline:
    1. pg_dump -> temp .sql file
    2. gzip -> temp .sql.gz file
    3. Upload to storage (Cloudinary or local)
    4. Clean up temp files
    """
    folder = _get_backup_folder()
    storage = _get_storage()

    # For FileSystemStorage (dev): path is relative to the storage location
    # which is already set to backups/, so we use tier/filename
    # For CloudinaryStorage (prod): path includes the folder prefix
    from django.core.files.storage import FileSystemStorage
    if isinstance(storage, FileSystemStorage):
        storage_path = f"{tier}/{filename}"
    else:
        storage_path = f"{folder}/{tier}/{filename}"

    tmp_dir = tempfile.mkdtemp(prefix=f"dbbackup_{tier}_")
    tmp_sql = os.path.join(tmp_dir, "dump.sql")
    tmp_gz = os.path.join(tmp_dir, "dump.sql.gz")
    tmp_enc = os.path.join(tmp_dir, "dump.sql.gz.enc")

    encrypt = _is_encryption_enabled()

    try:
        if not _run_pg_dump(tmp_sql):
            raise Exception(f"pg_dump failed for {tier} backup")

        compressed_size = _gzip_file(tmp_sql, tmp_gz)
        logger.info("[DBBACKUP] Compressed: %.2f KB", compressed_size / 1024)

        if encrypt:
            encrypted_size = _encrypt_file(tmp_gz, tmp_enc)
            logger.info("[DBBACKUP] Encrypted: %.2f KB", encrypted_size / 1024)
            upload_source = tmp_enc
            result_size = encrypted_size
        else:
            upload_source = tmp_gz
            result_size = compressed_size

        saved_path = _upload_to_storage(upload_source, storage_path)
        logger.info("[DBBACKUP] Uploaded to storage: %s", saved_path)

        return {
            "status": "ok",
            "path": saved_path,
            "tier": tier,
            "size_kb": round(result_size / 1024, 2),
            "encrypted": encrypt,
            "timestamp": datetime.now(datetime.timezone.utc).isoformat(),
        }
    finally:
        for tmp_file in (tmp_sql, tmp_gz, tmp_enc):
            try:
                if os.path.exists(tmp_file):
                    os.remove(tmp_file)
            except Exception:
                pass
        try:
            os.rmdir(tmp_dir)
        except Exception:
            pass


def _list_storage_files(tier):
    """
    List files in the storage backend for a given tier.
    Returns list of (filename, full_path) tuples.
    """
    folder = _get_backup_folder()
    storage = _get_storage()

    from django.core.files.storage import FileSystemStorage
    if isinstance(storage, FileSystemStorage):
        prefix = f"{tier}/"
    else:
        prefix = f"{folder}/{tier}/"

    try:
        dirs, files = storage.listdir(prefix)
        return [(f, f"{prefix}{f}") for f in files if f.endswith(".sql.gz")]
    except FileNotFoundError:
        logger.info("[DBBACKUP] Directory does not exist in storage: %s", prefix)
        return []
    except Exception as exc:
        logger.warning("[DBBACKUP] Could not list files in %s: %s", prefix, exc)
        return []


def _delete_storage_file(full_path):
    """Delete a file from the storage backend."""
    storage = _get_storage()
    try:
        storage.delete(full_path)
        logger.info("[DBBACKUP] Deleted: %s", full_path)
        return True
    except Exception as exc:
        logger.warning("[DBBACKUP] Could not delete %s: %s", full_path, exc)
        return False


def _parse_timestamp_from_filename(filename):
    """
    Parse a timestamp from a backup filename.
    Formats: YYYYMMDD_HHMMSS (hourly) or YYYYMM_01_HHMMSS (monthly)
    Returns datetime object or None.
    """
    base = filename.replace(".sql.gz", "")

    match = re.match(r"(\d{4})(\d{2})(\d{2})_(\d{2})(\d{2})(\d{2})", base)
    if match:
        try:
            return datetime(
                int(match.group(1)), int(match.group(2)), int(match.group(3)),
                int(match.group(4)), int(match.group(5)), int(match.group(6)),
            )
        except ValueError:
            return None

    match = re.match(r"(\d{4})(\d{2})_01_(\d{2})(\d{2})(\d{2})", base)
    if match:
        try:
            return datetime(
                int(match.group(1)), int(match.group(2)), 1,
                int(match.group(3)), int(match.group(4)), int(match.group(5)),
            )
        except ValueError:
            return None

    return None


# === TIER 1: ROLLING BACKUP (every 5 minutes - overwrites same file) ===

@shared_task(
    name="dbbackup.rolling_backup",
    bind=True,
    max_retries=2,
    default_retry_delay=30,
    queue="default",
)
def rolling_backup(self):
    """
    Create a rolling database backup that overwrites the same file every 5 minutes.
    File: {folder}/rolling/latest.sql.gz
    """
    try:
        result = _create_backup("rolling", "latest.sql.gz")
        logger.info("[DBBACKUP] Rolling backup complete: %s", result)
        return result
    except Exception as exc:
        logger.error("[DBBACKUP] Rolling backup failed: %s", exc)
        raise self.retry(countdown=30, exc=exc)


# === TIER 2: HOURLY BACKUP (every 1 hour - timestamped, 30-day retention) ===

@shared_task(
    name="dbbackup.hourly_backup",
    bind=True,
    max_retries=2,
    default_retry_delay=60,
    queue="default",
)
def hourly_backup(self):
    """
    Create an hourly timestamped database backup.
    File: {folder}/hourly/YYYYMMDD_HHMMSS.sql.gz
    24 files/day, cleaned up after 30 days.
    """
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    filename = f"{timestamp}.sql.gz"

    try:
        result = _create_backup("hourly", filename)
        logger.info("[DBBACKUP] Hourly backup complete: %s", result)
        return result
    except Exception as exc:
        logger.error("[DBBACKUP] Hourly backup failed: %s", exc)
        raise self.retry(countdown=60, exc=exc)


# === TIER 3: MONTHLY BACKUP (1st of each month - timestamped, 12-month retention) ===

@shared_task(
    name="dbbackup.monthly_backup",
    bind=True,
    max_retries=2,
    default_retry_delay=120,
    queue="default",
)
def monthly_backup(self):
    """
    Create a monthly timestamped database backup on the 1st of each month.
    File: {folder}/monthly/YYYYMM_01_HHMMSS.sql.gz
    Cleaned up after 365 days (12 months).
    """
    timestamp = datetime.now(datetime.timezone.utc).strftime("%Y%m_01_%H%M%S")
    filename = f"{timestamp}.sql.gz"

    try:
        result = _create_backup("monthly", filename)
        logger.info("[DBBACKUP] Monthly backup complete: %s", result)
        return result
    except Exception as exc:
        logger.error("[DBBACKUP] Monthly backup failed: %s", exc)
        raise self.retry(countdown=120, exc=exc)


# === CLEANUP TASK 1: Delete hourly backups older than 30 days ===

@shared_task(
    name="dbbackup.cleanup_hourly_backups",
    queue="cleanup",
)
def cleanup_hourly_backups():
    """
    Delete hourly backup files older than 30 days.
    Runs daily at 4 AM UTC via Celery Beat.
    """
    cutoff = datetime.now(datetime.timezone.utc) - timedelta(days=30)
    files = _list_storage_files("hourly")

    deleted_count = 0
    for filename, full_path in files:
        ts = _parse_timestamp_from_filename(filename)
        if ts and ts < cutoff:
            if _delete_storage_file(full_path):
                deleted_count += 1

    logger.info("[DBBACKUP] Hourly cleanup: deleted %d files older than %s", deleted_count, cutoff.date())

    return {
        "status": "ok",
        "deleted": deleted_count,
        "cutoff": cutoff.isoformat(),
        "tier": "hourly_cleanup",
    }


# === CLEANUP TASK 2: Delete monthly backups older than 365 days (12 months) ===

@shared_task(
    name="dbbackup.cleanup_monthly_backups",
    queue="cleanup",
)
def cleanup_monthly_backups():
    """
    Delete monthly backup files older than 365 days (12 months / 1 year).
    Runs monthly on the 2nd of each month via Celery Beat.
    """
    cutoff = datetime.now(datetime.timezone.utc) - timedelta(days=365)
    files = _list_storage_files("monthly")

    deleted_count = 0
    for filename, full_path in files:
        ts = _parse_timestamp_from_filename(filename)
        if ts and ts < cutoff:
            if _delete_storage_file(full_path):
                deleted_count += 1

    logger.info("[DBBACKUP] Monthly cleanup: deleted %d files older than %s", deleted_count, cutoff.date())

    return {
        "status": "ok",
        "deleted": deleted_count,
        "cutoff": cutoff.isoformat(),
        "tier": "monthly_cleanup",
    }
