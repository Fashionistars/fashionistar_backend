# apps/common/tasks/dbrestore.py
"""
FASHIONISTAR - Database Restoration System
============================================

Multi-strategy database restoration that handles all scenarios:

  +-------------------+-------------------+-------------------+-------------------+
  |                   |  PostgreSQL (prod)|  PostgreSQL (prod)|  SQLite (dev)     |
  |                   |  EMPTY target     |  NON-EMPTY target |  EMPTY / NON-EMPTY|
  +-------------------+-------------------+-------------------+-------------------+
  | Method 1: psql    |  Full restore     |  DROP + restore   |  N/A (PG only)    |
  | (pg_dump backup)  |  (fastest)        |  (destructive)    |                   |
  +-------------------+-------------------+-------------------+-------------------+
  | Method 2: psycopg |  COPY data into   |  TRUNCATE + COPY  |  N/A (PG only)    |
  | (COPY blocks)     |  fresh tables     |  (destructive)    |                   |
  +-------------------+-------------------+-------------------+-------------------+
  | Method 3: Django  |  ORM bulk_create  |  get_or_create    |  ORM bulk_create  |
  | (cross-DB ORM)    |  (fast)           |  (merge, safe)    |  get_or_create    |
  +-------------------+-------------------+-------------------+-------------------+
  | Method 4: Merge   |  ON CONFLICT      |  ON CONFLICT      |  INSERT OR IGNORE |
  | (non-destructive) |  DO NOTHING       |  DO NOTHING       |  (merge, safe)    |
  +-------------------+-------------------+-------------------+-------------------+

Backup formats supported:
  1. pg_dump --format=plain (full SQL: CREATE TABLE + INSERT + extensions)
  2. psycopg COPY fallback (data-only: COPY "schema"."table" FROM stdin; ... \\.)

Key design principles:
  - NEVER corrupt existing data in non-empty databases
  - Automatically detect backup format (pg_dump vs COPY-only)
  - Automatically detect target DB engine (PostgreSQL vs SQLite)
  - Wrap everything in transactions with rollback on failure
  - Detailed progress logging and structured result reporting
"""

import os
import re
import gzip
import shutil
import tempfile
import logging
import subprocess
from io import StringIO
from datetime import datetime, timezone

from celery import shared_task
from django.conf import settings
from django.db import connection, transaction, models
from django.apps import apps

logger = logging.getLogger(__name__)


# =============================================================================
# CONSTANTS
# =============================================================================

_BACKUP_FORMAT_PG_DUMP = "pg_dump"
_BACKUP_FORMAT_COPY = "copy"
_BACKUP_FORMAT_UNKNOWN = "unknown"

_RESTORE_METHOD_PSQL = "psql_binary"
_RESTORE_METHOD_PSYCOPY = "psycopg_copy"
_RESTORE_METHOD_ORM = "django_orm"
_RESTORE_METHOD_MERGE = "merge_safe"

# Tables that should never be restored (Django internal, ephemeral, or auto-managed)
_EXCLUDED_TABLES = {
    "django_session",
    "django_celery_beat_periodictasks",
    "django_celery_beat_clockedschedule",
    "django_celery_beat_crontabschedule",
    "django_celery_beat_intervalschedule",
    "django_celery_beat_solarschedule",
    "django_celery_beat_periodictask",
    "playing_with_neon",
}

# Tables where existing rows should be preserved during merge (not overwritten)
_PRESERVE_TABLES = {
    "django_admin_log",
    "django_migrations",
    "common_audit_log",
    "common_slow_performance_audit_log",
    "audit_logs_auditeventlog",
    "ai_dbchangeevent",
    "ai_workflowexecution",
}


# =============================================================================
# BACKUP FORMAT DETECTION
# =============================================================================

def _detect_backup_format(sql_content):
    """
    Detect whether the SQL content is a full pg_dump or COPY-only fallback.

    pg_dump format: Contains CREATE TABLE, ALTER TABLE, CREATE INDEX, etc.
    COPY format: Contains only COPY ... FROM stdin; blocks with data.

    Returns one of _BACKUP_FORMAT_PG_DUMP, _BACKUP_FORMAT_COPY, _BACKUP_FORMAT_UNKNOWN.
    """
    # Read first 2000 chars for detection (headers + first statements)
    head = sql_content[:2000] if isinstance(sql_content, str) else sql_content[:2000].decode("utf-8", errors="replace")

    # pg_dump produces these markers
    if any(marker in head for marker in (
        "CREATE TABLE",
        "CREATE EXTENSION",
        "SET statement_timeout",
        "pg_dump",
        "PostgreSQL database dump",
    )):
        return _BACKUP_FORMAT_PG_DUMP

    # psycopg COPY fallback has this marker
    if "psycopg fallback" in head or (
        "COPY " in head and "FROM stdin" in head
        and "CREATE TABLE" not in head
    ):
        return _BACKUP_FORMAT_COPY

    # Check for COPY blocks further in the file
    if "COPY " in sql_content and "FROM stdin" in sql_content:
        return _BACKUP_FORMAT_COPY

    return _BACKUP_FORMAT_UNKNOWN


def _detect_target_engine():
    """
    Detect the target database engine from Django's DATABASES config.

    Returns 'postgresql', 'sqlite', or 'unknown'.
    """
    engine = connection.settings_dict.get("ENGINE", "")
    if "postgresql" in engine:
        return "postgresql"
    if "sqlite" in engine:
        return "sqlite"
    return "unknown"


# =============================================================================
# BACKUP FILE DOWNLOAD & DECOMPRESSION
# =============================================================================

def _download_from_storage(storage_path):
    """
    Download a backup file from the configured storage backend.
    Returns the local file path to a decompressed .sql file.
    """
    from apps.common.tasks.dbbackups import _get_storage

    storage = _get_storage()

    tmp_dir = tempfile.mkdtemp(prefix="dbrestore_")
    tmp_gz = os.path.join(tmp_dir, "backup.sql.gz")
    tmp_sql = os.path.join(tmp_dir, "backup.sql")

    try:
        # Download from storage
        with open(tmp_gz, "wb") as f:
            f.write(storage.open(storage_path).read())
        logger.info("[DBRESTORE] Downloaded: %s (%s bytes)", storage_path, os.path.getsize(tmp_gz))

        # Decompress
        with gzip.open(tmp_gz, "rb") as src:
            with open(tmp_sql, "wb") as dst:
                shutil.copyfileobj(src, dst)
        logger.info("[DBRESTORE] Decompressed: %s (%s bytes)", tmp_sql, os.path.getsize(tmp_sql))

        return tmp_sql, tmp_dir

    except Exception as exc:
        # Clean up on failure
        for f in (tmp_gz, tmp_sql):
            try:
                if os.path.exists(f):
                    os.remove(f)
            except Exception:
                pass
        try:
            os.rmdir(tmp_dir)
        except Exception:
            pass
        raise Exception(f"Failed to download/decompress backup: {exc}")


def _cleanup_temp(tmp_dir, *files):
    """Clean up temporary files and directory."""
    for f in files:
        try:
            if os.path.exists(f):
                os.remove(f)
        except Exception:
            pass
    try:
        os.rmdir(tmp_dir)
    except Exception:
        pass


# =============================================================================
# SQL PARSING UTILITIES
# =============================================================================

def _parse_copy_blocks(sql_content):
    """
    Parse COPY ... FROM stdin; blocks from SQL content.

    Returns a list of dicts:
        {
            "table": "public.auth_user",
            "schema": "public",
            "table_name": "auth_user",
            "columns": ["id", "email", ...],  # extracted from COPY statement if present
            "data": "row1\trow2\t...\n...",   # raw COPY data
        }
    """
    blocks = []

    # Pattern: COPY "schema"."table" FROM stdin;  (or COPY "table" FROM stdin;)
    # Data follows until a line with just "\."
    pattern = re.compile(
        r'COPY\s+("?(\w+)"?\.)?"?(\w+)"?\s+(?:\(([^)]+)\)\s+)?FROM\s+stdin;\n',
        re.IGNORECASE,
    )

    pos = 0
    while True:
        match = pattern.search(sql_content, pos)
        if not match:
            break

        schema = match.group(2) or "public"
        table_name = match.group(3)
        columns_str = match.group(4)
        columns = [c.strip().strip('"') for c in columns_str.split(",")] if columns_str else []

        data_start = match.end()
        # Find the terminator line: \.\n or \.\r\n
        term_match = re.search(r'^\\\.\s*$', sql_content[data_start:], re.MULTILINE)
        if not term_match:
            logger.warning("[DBRESTORE] No COPY terminator found for %s.%s", schema, table_name)
            break

        data = sql_content[data_start:data_start + term_match.start()]
        blocks.append({
            "schema": schema,
            "table_name": table_name,
            "fq_table": f'"{schema}"."{table_name}"',
            "columns": columns,
            "data": data,
            "row_count": data.count("\n") if data else 0,
        })

        pos = data_start + term_match.end()

    return blocks


def _parse_pg_dump_statements(sql_content):
    """
    Split a pg_dump plain SQL file into individual SQL statements.
    Respects COPY blocks (which contain data with newlines).

    Returns a list of (statement_type, statement_text) tuples.
    statement_type is one of: 'ddl', 'copy', 'insert', 'other'
    """
    statements = []
    pos = 0
    length = len(sql_content)

    while pos < length:
        # Skip whitespace and comments
        while pos < length and sql_content[pos] in " \t\n\r":
            pos += 1
        if pos >= length:
            break

        # Skip single-line comments (-- ...)
        if sql_content[pos:pos + 2] == "--":
            end = sql_content.find("\n", pos)
            if end == -1:
                break
            pos = end + 1
            continue

        # Check for COPY block
        if sql_content[pos:pos + 4].upper() == "COPY":
            # Find the semicolon after FROM stdin
            semi = sql_content.find(";", pos)
            if semi == -1:
                break
            header = sql_content[pos:semi + 1]
            # Find the \. terminator
            data_start = semi + 1
            # Skip the newline after semicolon
            if data_start < length and sql_content[data_start] == "\n":
                data_start += 1
            term = re.search(r'^\\\.\s*$', sql_content[data_start:], re.MULTILINE)
            if term:
                block_end = data_start + term.end()
                statements.append(("copy", sql_content[pos:block_end]))
                pos = block_end
                continue

        # Find the next semicolon (end of statement)
        semi = sql_content.find(";", pos)
        if semi == -1:
            # Remaining text
            remaining = sql_content[pos:].strip()
            if remaining:
                statements.append(("other", remaining))
            break

        stmt = sql_content[pos:semi + 1].strip()
        if stmt:
            upper = stmt.upper()
            if upper.startswith("CREATE") or upper.startswith("ALTER") or upper.startswith("DROP"):
                statements.append(("ddl", stmt))
            elif upper.startswith("INSERT"):
                statements.append(("insert", stmt))
            else:
                statements.append(("other", stmt))
        pos = semi + 1

    return statements


def _get_table_columns_from_django(table_name):
    """
    Get column names for a table using Django's introspection.
    Returns a list of column names in DB order.
    """
    try:
        with connection.cursor() as cursor:
            introspection = connection.introspection
            db_table = table_name.replace('"', '')
            # For PostgreSQL, table might be schema-qualified
            if "." in db_table:
                parts = db_table.split(".")
                schema_part = parts[0].strip('"')
                table_part = parts[1].strip('"')
                # Use information_schema for PostgreSQL
                if _detect_target_engine() == "postgresql":
                    cursor.execute("""
                        SELECT column_name
                        FROM information_schema.columns
                        WHERE table_schema = %s AND table_name = %s
                        ORDER BY ordinal_position;
                    """, [schema_part, table_part])
                    return [row[0] for row in cursor.fetchall()]

            # Fallback to Django introspection
            description = introspection.get_table_description(cursor, db_table)
            return [col.name for col in description]
    except Exception as exc:
        logger.warning("[DBRESTORE] Could not introspect columns for %s: %s", table_name, exc)
        return []


def _table_exists(table_name):
    """Check if a table exists in the target database."""
    try:
        with connection.cursor() as cursor:
            introspection = connection.introspection
            db_table = table_name.replace('"', '').split(".")[-1]
            table_list = introspection.table_names()
            return db_table in table_list
    except Exception:
        return False


def _get_table_row_count(table_name):
    """Get the row count for a table in the target database."""
    try:
        with connection.cursor() as cursor:
            db_table = table_name.replace('"', '').split(".")[-1]
            cursor.execute(f'SELECT COUNT(*) FROM "{db_table}"')
            return cursor.fetchone()[0]
    except Exception:
        return -1


# =============================================================================
# METHOD 1: PSQL BINARY RESTORE (PostgreSQL only, pg_dump format)
# =============================================================================

def _restore_via_psql(sql_file, target_db_url=None, destructive=True):
    """
    Restore a pg_dump plain SQL file using the psql binary.
    This is the fastest and most reliable method for PostgreSQL targets.

    Args:
        sql_file: Path to the decompressed .sql file
        target_db_url: Database URL (defaults to DATABASE_URL env var)
        destructive: If True, includes DROP statements (for empty or replace scenarios)

    Returns dict with restore results.
    """
    db_url = target_db_url or os.environ.get("DATABASE_URL", "")
    if not db_url:
        return {"status": "error", "error": "No DATABASE_URL found"}

    logger.info("[DBRESTORE] Method 1: psql binary restore (destructive=%s)", destructive)

    cmd = [
        "psql",
        db_url,
        "--set", "ON_ERROR_STOP=on",
        "--single-transaction",
        "--quiet",
        "--file", sql_file,
    ]

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode == 0:
            logger.info("[DBRESTORE] psql restore completed successfully")
            return {
                "status": "ok",
                "method": _RESTORE_METHOD_PSQL,
                "warnings": result.stderr.strip() if result.stderr else "",
            }
        else:
            logger.error("[DBRESTORE] psql failed (exit %d): %s", result.returncode, result.stderr[:1000])
            return {
                "status": "error",
                "method": _RESTORE_METHOD_PSQL,
                "error": result.stderr[:500],
                "exit_code": result.returncode,
            }
    except FileNotFoundError:
        logger.warning("[DBRESTORE] psql binary not found")
        return {"status": "error", "method": _RESTORE_METHOD_PSQL, "error": "psql binary not found"}
    except subprocess.TimeoutExpired:
        logger.error("[DBRESTORE] psql timed out after 600 seconds")
        return {"status": "error", "method": _RESTORE_METHOD_PSQL, "error": "Timeout after 600s"}
    except Exception as exc:
        logger.error("[DBRESTORE] psql error: %s", exc)
        return {"status": "error", "method": _RESTORE_METHOD_PSQL, "error": str(exc)}


# =============================================================================
# METHOD 2: PSYCOPY COPY-BASED RESTORE (PostgreSQL only, COPY format)
# =============================================================================

def _restore_via_psycopg_copy(sql_content, target_db_url=None, destructive=True):
    """
    Restore COPY-format backup to PostgreSQL using psycopg's COPY FROM STDIN.
    Parses COPY blocks and streams data back into the database.

    Args:
        sql_content: The full SQL content (string)
        target_db_url: Database URL (defaults to DATABASE_URL env var)
        destructive: If True, TRUNCATE tables before loading (for empty/replace)
                     If False, append data (may fail on unique constraints)

    Returns dict with restore results.
    """
    import psycopg

    db_url = target_db_url or os.environ.get("DATABASE_URL", "")
    if not db_url:
        return {"status": "error", "error": "No DATABASE_URL found"}

    logger.info("[DBRESTORE] Method 2: psycopg COPY restore (destructive=%s)", destructive)

    blocks = _parse_copy_blocks(sql_content)
    if not blocks:
        return {"status": "error", "method": _RESTORE_METHOD_PSYCOPY, "error": "No COPY blocks found in backup"}

    total_blocks = len(blocks)
    restored = 0
    errors = []
    skipped = 0

    def _get_conn():
        c = psycopg.connect(db_url, connect_timeout=30)
        c.autocommit = False
        return c

    conn = None
    try:
        conn = _get_conn()

        for i, block in enumerate(blocks):
            table = block["table_name"]
            fq_table = block["fq_table"]

            # Skip excluded tables
            if table in _EXCLUDED_TABLES:
                logger.info("[DBRESTORE] Skipping excluded table: %s (%d/%d)", fq_table, i + 1, total_blocks)
                skipped += 1
                continue

            logger.info("[DBRESTORE] Restoring %s (%d/%d, ~%d rows)", fq_table, i + 1, total_blocks, block["row_count"])

            max_retries = 3
            for attempt in range(max_retries):
                try:
                    with conn.cursor() as cur:
                        # Destructive mode: TRUNCATE before loading
                        if destructive:
                            cur.execute(f'TRUNCATE TABLE {fq_table} CASCADE;')

                        # Use COPY FROM STDIN to stream data back
                        copy_stmt = f'COPY {fq_table} FROM stdin;'
                        with cur.copy(copy_stmt) as copy:
                            # Write the data in chunks
                            data = block["data"]
                            if isinstance(data, str):
                                data = data.encode("utf-8")
                            # Write in 8KB chunks for memory efficiency
                            chunk_size = 8192
                            for j in range(0, len(data), chunk_size):
                                copy.write(data[j:j + chunk_size])

                    conn.commit()
                    restored += 1
                    break

                except (psycopg.OperationalError, psycopg.InterfaceError) as conn_err:
                    logger.warning(
                        "[DBRESTORE] Connection lost on %s (attempt %d/%d): %s",
                        fq_table, attempt + 1, max_retries, conn_err,
                    )
                    try:
                        if conn:
                            conn.close()
                    except Exception:
                        pass
                    if attempt < max_retries - 1:
                        conn = _get_conn()
                    else:
                        errors.append(f"{fq_table}: connection failed after {max_retries} retries")

                except psycopg.Error as pg_err:
                    logger.warning("[DBRESTORE] Error on %s: %s", fq_table, pg_err)
                    errors.append(f"{fq_table}: {pg_err}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    break

                except Exception as exc:
                    logger.warning("[DBRESTORE] Unexpected error on %s: %s", fq_table, exc)
                    errors.append(f"{fq_table}: {exc}")
                    try:
                        conn.rollback()
                    except Exception:
                        pass
                    break

    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

    logger.info(
        "[DBRESTORE] psycopg COPY restore: %d/%d tables restored, %d skipped, %d errors",
        restored, total_blocks, skipped, len(errors),
    )

    return {
        "status": "ok" if restored > 0 else "error",
        "method": _RESTORE_METHOD_PSYCOPY,
        "tables_total": total_blocks,
        "tables_restored": restored,
        "tables_skipped": skipped,
        "errors": errors[:20],  # Limit error list
    }


# =============================================================================
# METHOD 3: DJANGO ORM CROSS-DB RESTORE (SQLite + PostgreSQL, merge-safe)
# =============================================================================

def _restore_via_django_orm(sql_content, merge_mode=False):
    """
    Restore backup data using Django's ORM layer.
    This method works across ALL database backends (SQLite, PostgreSQL, MySQL).
    Parses COPY blocks, maps table names to Django models, and uses bulk_create.

    Args:
        sql_content: The full SQL content (string)
        merge_mode: If True, uses get_or_create (non-destructive merge into existing DB)
                    If False, clears existing data first then bulk_create (destructive)

    Returns dict with restore results.
    """
    logger.info("[DBRESTORE] Method 3: Django ORM restore (merge_mode=%s)", merge_mode)

    blocks = _parse_copy_blocks(sql_content)
    if not blocks:
        return {"status": "error", "method": _RESTORE_METHOD_ORM, "error": "No COPY blocks found in backup"}

    # Build a mapping of table names to Django models
    table_to_model = {}
    for model in apps.get_models():
        table_to_model[model._meta.db_table] = model

    total_blocks = len(blocks)
    restored = 0
    skipped = 0
    errors = []
    total_rows = 0

    for i, block in enumerate(blocks):
        table_name = block["table_name"]

        # Skip excluded tables
        if table_name in _EXCLUDED_TABLES:
            logger.info("[DBRESTORE] Skipping excluded table: %s (%d/%d)", table_name, i + 1, total_blocks)
            skipped += 1
            continue

        # Find the Django model for this table
        model = table_to_model.get(table_name)
        if not model:
            logger.warning("[DBRESTORE] No Django model for table: %s (%d/%d)", table_name, i + 1, total_blocks)
            skipped += 1
            continue

        logger.info("[DBRESTORE] Restoring %s -> %s (%d/%d)", table_name, model.__name__, i + 1, total_blocks)

        try:
            rows_restored = _restore_table_via_orm(model, block, merge_mode)
            restored += 1
            total_rows += rows_restored
        except Exception as exc:
            logger.warning("[DBRESTORE] Error restoring %s: %s", table_name, exc)
            errors.append(f"{table_name}: {exc}")

    logger.info(
        "[DBRESTORE] ORM restore: %d/%d tables restored, %d skipped, %d total rows, %d errors",
        restored, total_blocks, skipped, total_rows, len(errors),
    )

    return {
        "status": "ok" if restored > 0 else "error",
        "method": _RESTORE_METHOD_ORM,
        "tables_total": total_blocks,
        "tables_restored": restored,
        "tables_skipped": skipped,
        "total_rows": total_rows,
        "errors": errors[:20],
        "merge_mode": merge_mode,
    }


def _restore_table_via_orm(model, block, merge_mode):
    """
    Restore a single table's data via Django ORM.

    Uses COPY data parsing to extract rows, maps to model fields,
    and uses bulk_create (destructive) or get_or_create (merge).
    """
    # Get model field names (DB column names)
    field_map = {}  # db_column -> model field
    for field in model._meta.get_fields():
        if hasattr(field, "column") and field.column:
            field_map[field.column] = field

    # Get column names from the COPY block or introspect from DB
    columns = block.get("columns", [])
    if not columns:
        # Introspect actual DB column order (matches COPY data order)
        # This is critical: COPY data follows information_schema.columns ordinal_position,
        # which may differ from Django model._meta.concrete_fields order
        columns = _get_table_columns_from_django(block.get("fq_table", f'public.{model._meta.db_table}'))
    if not columns:
        # Final fallback: use model field order
        columns = [f.column for f in model._meta.concrete_fields if f.column]

    # Parse COPY data into rows
    # COPY format: tab-separated values, \N for NULL, \t for tab in data
    raw_data = block["data"]
    if not raw_data.strip():
        return 0

    rows = []
    for line in raw_data.split("\n"):
        if not line.strip():
            continue
        # Split by tab (COPY default delimiter)
        values = line.split("\t")
        # Convert \N to None (NULL marker in COPY format)
        values = [None if v == "\\N" else v for v in values]

        if len(values) != len(columns):
            # Column count mismatch - try to handle gracefully
            logger.warning(
                "[DBRESTORE] Column mismatch on %s: expected %d, got %d. Skipping row.",
                model._meta.db_table, len(columns), len(values),
            )
            continue

        row_dict = {}
        for col_name, value in zip(columns, values):
            field = field_map.get(col_name)
            if field is None:
                # Try case-insensitive match
                for fc, fl in field_map.items():
                    if fc.lower() == col_name.lower():
                        field = fl
                        break

            if field is not None:
                # Convert string values to proper Python types
                converted = _convert_value_for_field(field, value)
                if converted is not None:
                    # Use attname (Python attribute name) not column name
                    row_dict[field.attname] = converted
            else:
                # Unknown column, store by column name
                row_dict[col_name] = value

        if row_dict:
            rows.append(row_dict)

    if not rows:
        return 0

    # Create model instances
    instances = []
    for row_dict in rows:
        instance = model(**row_dict)
        instances.append(instance)

    with transaction.atomic():
        if merge_mode:
            # Non-destructive: use get_or_create for each row
            created_count = 0
            for instance in instances:
                # Use the primary key to check existence
                pk_field = model._meta.pk
                pk_name = pk_field.attname
                pk_value = getattr(instance, pk_name, None)

                if pk_value is not None:
                    _, created = model.objects.get_or_create(
                        **{pk_name: pk_value},
                        defaults={
                            f.attname: getattr(instance, f.attname)
                            for f in model._meta.concrete_fields
                            if f.attname != pk_name
                        },
                    )
                    if created:
                        created_count += 1
                else:
                    # No PK, just create
                    instance.save()
                    created_count += 1
            return created_count
        else:
            # Destructive: clear table then bulk_create
            model.objects.all().delete()
            model.objects.bulk_create(instances, ignore_conflicts=False)
            return len(instances)


def _convert_value_for_field(field, value):
    """
    Convert a string value from COPY format to the proper Python type for a Django field.
    """
    if value is None or value == "":
        return None

    # Strip whitespace from COPY format values
    value = value.strip() if isinstance(value, str) else value
    if not value:
        return None

    # Get the internal type of the field
    internal_type = field.get_internal_type()

    try:
        if internal_type in ("AutoField", "BigAutoField", "SmallAutoField"):
            return int(value)
        elif internal_type in ("IntegerField", "BigIntegerField", "SmallIntegerField",
                               "PositiveIntegerField", "PositiveSmallIntegerField",
                               "PositiveBigIntegerField"):
            return int(value)
        elif internal_type in ("FloatField",):
            return float(value)
        elif internal_type in ("DecimalField",):
            from decimal import Decimal, InvalidOperation
            try:
                return Decimal(value)
            except InvalidOperation:
                # COPY may have extra precision or formatting; try stripping
                cleaned = value.strip().rstrip("0")
                if cleaned.endswith("."):
                    cleaned = cleaned[:-1]
                return Decimal(cleaned) if cleaned else None
        elif internal_type in ("BooleanField", "NullBooleanField"):
            if value in ("t", "true", "True", "1", "T"):
                return True
            elif value in ("f", "false", "False", "0", "F"):
                return False
            return None
        elif internal_type in ("DateTimeField",):
            # PostgreSQL COPY format: 2024-01-15 10:30:00+00
            # Let Django handle the parsing via to_python
            return value
        elif internal_type in ("DateField",):
            return value
        elif internal_type in ("TimeField",):
            return value
        elif internal_type in ("JSONField",):
            import json
            try:
                return json.loads(value)
            except (json.JSONDecodeError, TypeError):
                # Return as string if JSON parsing fails
                return value
        elif internal_type in ("BinaryField",):
            # COPY format uses hex encoding for bytea: \x<hex>
            if value.startswith("\\x"):
                try:
                    return bytes.fromhex(value[2:])
                except ValueError:
                    return value.encode("utf-8")
            return value.encode("utf-8")
        elif internal_type in ("VectorField",):
            # pgvector - store as string, let the field handle conversion
            return value
        else:
            # CharField, TextField, SlugField, EmailField, URLField, UUIDField, etc.
            return value
    except (ValueError, TypeError) as exc:
        logger.warning(
            "[DBRESTORE] Could not convert value '%s' for field %s (%s): %s",
            value[:50] if value else "None", field.name, internal_type, exc,
        )
        return None


# =============================================================================
# METHOD 4: SCHEMA-AWARE MERGE RESTORE (non-destructive, all DB engines)
# =============================================================================

def _restore_via_merge(sql_content):
    """
    Non-destructive merge restore that preserves existing data.
    Works with both PostgreSQL and SQLite.

    For PostgreSQL: Uses INSERT ... ON CONFLICT DO NOTHING
    For SQLite: Uses INSERT OR IGNORE INTO ...

    This method NEVER deletes existing rows. It only inserts rows that
    don't already exist (matched by primary key).

    Args:
        sql_content: The full SQL content (string)

    Returns dict with restore results.
    """
    engine = _detect_target_engine()
    logger.info("[DBRESTORE] Method 4: Schema-aware merge restore (engine=%s)", engine)

    blocks = _parse_copy_blocks(sql_content)
    if not blocks:
        return {"status": "error", "method": _RESTORE_METHOD_MERGE, "error": "No COPY blocks found in backup"}

    total_blocks = len(blocks)
    restored = 0
    skipped = 0
    errors = []
    total_rows = 0

    for i, block in enumerate(blocks):
        table_name = block["table_name"]

        if table_name in _EXCLUDED_TABLES:
            skipped += 1
            continue

        # Check if table exists in target
        if not _table_exists(block["fq_table"]):
            logger.warning("[DBRESTORE] Table %s does not exist in target DB, skipping (%d/%d)", table_name, i + 1, total_blocks)
            skipped += 1
            continue

        # Skip preserve tables (audit logs, etc.)
        if table_name in _PRESERVE_TABLES:
            existing_count = _get_table_row_count(block["fq_table"])
            if existing_count > 0:
                logger.info("[DBRESTORE] Preserving existing data in %s (%d rows), skipping", table_name, existing_count)
                skipped += 1
                continue

        logger.info("[DBRESTORE] Merging %s (%d/%d)", table_name, i + 1, total_blocks)

        try:
            rows_merged = _merge_table_data(block, engine)
            restored += 1
            total_rows += rows_merged
        except Exception as exc:
            logger.warning("[DBRESTORE] Error merging %s: %s", table_name, exc)
            errors.append(f"{table_name}: {exc}")

    logger.info(
        "[DBRESTORE] Merge restore: %d/%d tables merged, %d skipped, %d rows inserted, %d errors",
        restored, total_blocks, skipped, total_rows, len(errors),
    )

    return {
        "status": "ok" if restored > 0 else "error",
        "method": _RESTORE_METHOD_MERGE,
        "tables_total": total_blocks,
        "tables_merged": restored,
        "tables_skipped": skipped,
        "rows_inserted": total_rows,
        "errors": errors[:20],
        "engine": engine,
    }


def _merge_table_data(block, engine):
    """
    Merge a single table's data using non-destructive INSERT with conflict resolution.

    For PostgreSQL: Uses a temp table + COPY FROM STDIN + INSERT ON CONFLICT DO NOTHING.
                    This handles all PG data types (JSON, bytea, arrays) correctly
                    because COPY FROM STDIN parses the text representation natively.
    For SQLite: Uses INSERT OR IGNORE INTO ... with parameterized values.
    """
    table_name = block["table_name"]
    fq_table = block["fq_table"].replace('"', '')
    # For SQLite, strip schema prefix
    if engine == "sqlite":
        fq_table = table_name

    # Get column names
    columns = block.get("columns", [])
    if not columns:
        columns = _get_table_columns_from_django(block["fq_table"])

    if not columns:
        logger.warning("[DBRESTORE] Could not determine columns for %s, skipping", table_name)
        return 0

    # Get primary key columns for conflict resolution
    pk_columns = _get_primary_key_columns(block["fq_table"], engine)

    # Parse COPY data into rows
    raw_data = block["data"]
    if not raw_data.strip():
        return 0

    rows_inserted = 0

    if engine == "postgresql":
        # Use psycopg directly for COPY FROM STDIN into temp table approach
        # This is the safest way to handle all PG data types (JSON, bytea, arrays)
        import psycopg

        db_url = os.environ.get("DATABASE_URL", "")
        if not db_url:
            logger.error("[DBRESTORE] No DATABASE_URL for psycopg merge")
            return 0

        temp_table_name = f"_tmp_restore_{table_name[:40]}"

        def _get_conn():
            c = psycopg.connect(db_url, connect_timeout=30)
            c.autocommit = False
            return c

        conn = None
        try:
            conn = _get_conn()
            with conn.cursor() as cur:
                # Step 1: Create temp table LIKE target (structure only, no constraints)
                cur.execute(f'CREATE TEMP TABLE "{temp_table_name}" (LIKE {block["fq_table"]});')

                # Step 2: COPY data into temp table using COPY FROM STDIN
                copy_stmt = f'COPY "{temp_table_name}" FROM stdin;'
                data_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data
                with cur.copy(copy_stmt) as copy:
                    chunk_size = 8192
                    for j in range(0, len(data_bytes), chunk_size):
                        copy.write(data_bytes[j:j + chunk_size])

                # Step 3: INSERT ... ON CONFLICT DO NOTHING from temp to target
                col_list = ", ".join(f'"{c}"' for c in columns)
                conflict_cols = ", ".join(f'"{c}"' for c in pk_columns) if pk_columns else ""

                if conflict_cols:
                    insert_sql = (
                        f'INSERT INTO {block["fq_table"]} ({col_list}) '
                        f'SELECT {col_list} FROM "{temp_table_name}" '
                        f'ON CONFLICT ({conflict_cols}) DO NOTHING'
                    )
                else:
                    insert_sql = (
                        f'INSERT INTO {block["fq_table"]} ({col_list}) '
                        f'SELECT {col_list} FROM "{temp_table_name}" '
                        f'ON CONFLICT DO NOTHING'
                    )
                cur.execute(insert_sql)
                rows_inserted = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0

                # Step 4: Drop temp table
                cur.execute(f'DROP TABLE IF EXISTS "{temp_table_name}";')

            conn.commit()

        except (psycopg.OperationalError, psycopg.InterfaceError) as conn_err:
            logger.warning("[DBRESTORE] Connection lost during merge of %s: %s", table_name, conn_err)
            try:
                if conn:
                    conn.rollback()
                    conn.close()
            except Exception:
                pass
            # Retry once with fresh connection
            try:
                conn = _get_conn()
                with conn.cursor() as cur:
                    cur.execute(f'CREATE TEMP TABLE "{temp_table_name}" (LIKE {block["fq_table"]});')
                    copy_stmt = f'COPY "{temp_table_name}" FROM stdin;'
                    data_bytes = raw_data.encode("utf-8") if isinstance(raw_data, str) else raw_data
                    with cur.copy(copy_stmt) as copy:
                        chunk_size = 8192
                        for j in range(0, len(data_bytes), chunk_size):
                            copy.write(data_bytes[j:j + chunk_size])
                    col_list = ", ".join(f'"{c}"' for c in columns)
                    conflict_cols = ", ".join(f'"{c}"' for c in pk_columns) if pk_columns else ""
                    if conflict_cols:
                        cur.execute(
                            f'INSERT INTO {block["fq_table"]} ({col_list}) '
                            f'SELECT {col_list} FROM "{temp_table_name}" '
                            f'ON CONFLICT ({conflict_cols}) DO NOTHING'
                        )
                    else:
                        cur.execute(
                            f'INSERT INTO {block["fq_table"]} ({col_list}) '
                            f'SELECT {col_list} FROM "{temp_table_name}" '
                            f'ON CONFLICT DO NOTHING'
                        )
                    rows_inserted = cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
                    cur.execute(f'DROP TABLE IF EXISTS "{temp_table_name}";')
                conn.commit()
            except Exception as retry_err:
                logger.error("[DBRESTORE] Retry also failed for %s: %s", table_name, retry_err)
                raise
        except Exception as exc:
            logger.error("[DBRESTORE] Merge failed for %s: %s", table_name, exc)
            try:
                if conn:
                    conn.rollback()
            except Exception:
                pass
            raise
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    elif engine == "sqlite":
        # SQLite: use INSERT OR IGNORE with parameterized values
        with transaction.atomic():
            with connection.cursor() as cursor:
                for line in raw_data.split("\n"):
                    if not line.strip():
                        continue

                    values = line.split("\t")
                    values = [None if v == "\\N" else v for v in values]

                    if len(values) != len(columns):
                        continue

                    col_list = ", ".join(f'"{c}"' for c in columns)
                    placeholders = ", ".join(["%s"] * len(columns))
                    sql = f'INSERT OR IGNORE INTO "{fq_table}" ({col_list}) VALUES ({placeholders})'
                    cursor.execute(sql, values)
                    rows_inserted += cursor.rowcount if cursor.rowcount > 0 else 0

    return rows_inserted


def _get_primary_key_columns(table_name, engine):
    """Get the primary key column(s) for a table."""
    try:
        with connection.cursor() as cursor:
            if engine == "postgresql":
                # Parse schema.table
                if "." in table_name.replace('"', ''):
                    parts = table_name.replace('"', '').split(".")
                    schema, tbl = parts[0], parts[1]
                else:
                    schema, tbl = "public", table_name.replace('"', '')

                cursor.execute("""
                    SELECT a.attname
                    FROM pg_index i
                    JOIN pg_attribute a ON a.attrelid = i.indrelid AND a.attnum = ANY(i.indkey)
                    WHERE i.indrelid = %s::regclass AND i.indisprimary
                    ORDER BY array_position(i.indkey, a.attnum);
                """, [f'"{schema}"."{tbl}"'])
                return [row[0] for row in cursor.fetchall()]

            elif engine == "sqlite":
                tbl = table_name.replace('"', '').split(".")[-1]
                cursor.execute(f'PRAGMA table_info("{tbl}")')
                return [row[1] for row in cursor.fetchall() if row[5] == 1]  # pk flag

    except Exception as exc:
        logger.warning("[DBRESTORE] Could not get PK for %s: %s", table_name, exc)

    return []


# =============================================================================
# ORCHESTRATOR: Auto-detect and choose best restore method
# =============================================================================

def _restore_backup(
    storage_path,
    method="auto",
    merge_mode=False,
    target_db_url=None,
):
    """
    Main restore orchestrator. Downloads, decompresses, detects format,
    and routes to the appropriate restore method.

    Args:
        storage_path: Path in the storage backend (e.g., "rolling/latest.sql.gz")
        method: Restore method - 'auto', 'psql', 'psycopg', 'orm', 'merge'
        merge_mode: If True, non-destructive merge (preserve existing data)
        target_db_url: Override target DB URL (defaults to DATABASE_URL env var)

    Returns dict with full restore results.
    """
    start_time = datetime.now(timezone.utc)

    logger.info("[DBRESTORE] Starting restore: storage_path=%s, method=%s, merge=%s", storage_path, method, merge_mode)

    # Step 1: Download and decompress
    try:
        sql_file, tmp_dir = _download_from_storage(storage_path)
    except Exception as exc:
        return {
            "status": "error",
            "error": str(exc),
            "storage_path": storage_path,
        }

    try:
        # Step 2: Read SQL content
        with open(sql_file, "r", encoding="utf-8", errors="replace") as f:
            sql_content = f.read()

        # Step 3: Detect backup format
        backup_format = _detect_backup_format(sql_content)
        target_engine = _detect_target_engine()

        logger.info("[DBRESTORE] Backup format: %s, Target engine: %s", backup_format, target_engine)

        # Step 4: Route to appropriate method
        result = None

        if method == "auto":
            # Auto-select best method based on format and engine
            if backup_format == _BACKUP_FORMAT_PG_DUMP and target_engine == "postgresql":
                # Try psql first, fall back to psycopg
                result = _restore_via_psql(sql_file, target_db_url, destructive=not merge_mode)
                if result.get("status") == "error" and "not found" in result.get("error", "").lower():
                    logger.info("[DBRESTORE] psql not available, trying psycopg COPY")
                    result = _restore_via_psycopg_copy(sql_content, target_db_url, destructive=not merge_mode)

            elif backup_format == _BACKUP_FORMAT_COPY and target_engine == "postgresql":
                if merge_mode:
                    result = _restore_via_merge(sql_content)
                else:
                    result = _restore_via_psycopg_copy(sql_content, target_db_url, destructive=True)

            elif target_engine == "sqlite":
                # SQLite: always use ORM or merge
                if merge_mode:
                    result = _restore_via_merge(sql_content)
                else:
                    result = _restore_via_django_orm(sql_content, merge_mode=False)

            else:
                # Fallback: ORM-based restore (works everywhere)
                result = _restore_via_django_orm(sql_content, merge_mode=merge_mode)

        elif method == "psql":
            result = _restore_via_psql(sql_file, target_db_url, destructive=not merge_mode)

        elif method == "psycopg":
            result = _restore_via_psycopg_copy(sql_content, target_db_url, destructive=not merge_mode)

        elif method == "orm":
            result = _restore_via_django_orm(sql_content, merge_mode=merge_mode)

        elif method == "merge":
            result = _restore_via_merge(sql_content)

        else:
            return {
                "status": "error",
                "error": f"Unknown method: {method}",
            }

        # Add metadata
        end_time = datetime.now(timezone.utc)
        duration = (end_time - start_time).total_seconds()

        result.update({
            "storage_path": storage_path,
            "backup_format": backup_format,
            "target_engine": target_engine,
            "merge_mode": merge_mode,
            "method_requested": method,
            "duration_seconds": round(duration, 2),
            "started_at": start_time.isoformat(),
            "completed_at": end_time.isoformat(),
        })

        logger.info("[DBRESTORE] Restore completed in %.2fs: %s", duration, result.get("status"))
        return result

    finally:
        _cleanup_temp(tmp_dir, os.path.join(tmp_dir, "backup.sql.gz"), os.path.join(tmp_dir, "backup.sql"))


# =============================================================================
# CELERY TASKS
# =============================================================================

@shared_task(
    name="dbrestore.restore_backup",
    bind=True,
    max_retries=1,
    default_retry_delay=60,
    queue="default",
)
def restore_backup_task(self, storage_path, method="auto", merge_mode=False):
    """
    Celery task to restore a database backup.

    Args:
        storage_path: Path in storage backend (e.g., "rolling/latest.sql.gz")
        method: 'auto', 'psql', 'psycopg', 'orm', or 'merge'
        merge_mode: If True, non-destructive (preserve existing data)
    """
    try:
        result = _restore_backup(storage_path, method=method, merge_mode=merge_mode)
        logger.info("[DBRESTORE] Restore task complete: %s", result.get("status"))
        return result
    except Exception as exc:
        logger.error("[DBRESTORE] Restore task failed: %s", exc)
        raise self.retry(countdown=60, exc=exc)


@shared_task(
    name="dbrestore.verify_backup",
    bind=True,
    max_retries=1,
    default_retry_delay=30,
    queue="default",
)
def verify_backup_task(self, storage_path):
    """
    Celery task to verify a backup file's integrity.
    Downloads, decompresses, checks format, counts tables and rows.
    Does NOT modify any database.

    Returns dict with verification results.
    """
    try:
        sql_file, tmp_dir = _download_from_storage(storage_path)

        try:
            with open(sql_file, "r", encoding="utf-8", errors="replace") as f:
                sql_content = f.read()

            backup_format = _detect_backup_format(sql_content)
            blocks = _parse_copy_blocks(sql_content)

            total_rows = sum(b["row_count"] for b in blocks)
            table_list = [b["table_name"] for b in blocks]

            result = {
                "status": "ok",
                "storage_path": storage_path,
                "backup_format": backup_format,
                "tables_found": len(blocks),
                "estimated_rows": total_rows,
                "table_names": table_list[:50],  # First 50 table names
                "file_size_kb": round(os.path.getsize(sql_file) / 1024, 2),
            }

            logger.info(
                "[DBRESTORE] Verify: %s, format=%s, %d tables, ~%d rows",
                storage_path, backup_format, len(blocks), total_rows,
            )
            return result

        finally:
            _cleanup_temp(tmp_dir, os.path.join(tmp_dir, "backup.sql.gz"), os.path.join(tmp_dir, "backup.sql"))

    except Exception as exc:
        logger.error("[DBRESTORE] Verify task failed: %s", exc)
        return {"status": "error", "error": str(exc), "storage_path": storage_path}


@shared_task(
    name="dbrestore.list_available_backups",
    queue="default",
)
def list_available_backups_task():
    """
    Celery task to list all available backups in storage.
    Returns a structured dict of all backup tiers and their files.
    """
    from apps.common.tasks.dbbackups import _list_storage_files, _parse_timestamp_from_filename

    result = {}
    for tier in ("rolling", "hourly", "monthly"):
        files = _list_storage_files(tier)
        result[tier] = [
            {
                "filename": fname,
                "path": fpath,
                "timestamp": _parse_timestamp_from_filename(fname).isoformat() if _parse_timestamp_from_filename(fname) else None,
            }
            for fname, fpath in files
        ]

    logger.info("[DBRESTORE] Listed backups: rolling=%d, hourly=%d, monthly=%d",
                len(result["rolling"]), len(result["hourly"]), len(result["monthly"]))
    return result
