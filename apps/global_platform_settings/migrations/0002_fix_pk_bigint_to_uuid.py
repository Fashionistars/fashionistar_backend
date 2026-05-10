# apps/global_platform_settings/migrations/0002_fix_pk_bigint_to_uuid.py
"""
Hand-authored migration — global_platform_settings 0002

Background
----------
The `0001_initial` migration was applied to the database when the ``id`` field
was still a ``BigAutoField`` (bigint).  The migration file was subsequently
hand-edited to use ``UUIDField`` to align with the ``TimeStampedModel`` base
class, but the underlying PostgreSQL table was never updated.

PostgreSQL cannot cast ``bigint`` to ``uuid`` directly
(``ALTER COLUMN "id" TYPE uuid USING "id"::uuid`` raises
``cannot cast type bigint to uuid``).

Safe resolution for singleton config tables
-------------------------------------------
The ``PlatformSettings`` model is a singleton — at most one admin-only row with
no FK references from other tables.  Zero business data is stored here.

Steps:
  1. ``TRUNCATE`` the table (the post_migrate seeder recreates the row).
  2. Drop the old bigint PK constraint and column.
  3. Add a new ``uuid`` PK column with ``gen_random_uuid()`` default.

The ``AlterField`` state operation after the ``RunSQL`` is essential so
Django's migration state graph agrees the ``id`` field is now a ``UUIDField``
(preventing a spurious 0003 being generated next time).
"""
from __future__ import annotations

import uuid6
from django.db import migrations, models

_TABLE = "global_platform_settings_platformsettings"

_FORWARD_SQL = f"""
-- Step 1: Truncate singleton rows (seeder re-creates on next startup)
TRUNCATE TABLE "{_TABLE}" RESTART IDENTITY CASCADE;
-- Step 2: Drop existing bigint PK
ALTER TABLE "{_TABLE}" DROP CONSTRAINT IF EXISTS "{_TABLE}_pkey";
ALTER TABLE "{_TABLE}" DROP COLUMN IF EXISTS "id";
-- Step 3: Add uuid PK column
ALTER TABLE "{_TABLE}" ADD COLUMN "id" uuid NOT NULL DEFAULT gen_random_uuid();
ALTER TABLE "{_TABLE}" ADD PRIMARY KEY ("id");
"""


class Migration(migrations.Migration):
    """
    Fix the ``id`` column type from ``bigint`` → ``uuid`` for PlatformSettings.

    This is required because the initial migration was applied to the database
    before the ``id`` field was changed from ``BigAutoField`` to ``UUIDField``.
    """

    dependencies = [
        ("global_platform_settings", "0001_initial"),
    ]

    operations = [
        # ── 1. Fix the DB column type via raw DDL ─────────────────────────────
        migrations.RunSQL(
            sql=_FORWARD_SQL,
            reverse_sql=migrations.RunSQL.noop,
        ),
        # ── 2. Sync Django ORM state with the new column type ─────────────────
        migrations.AlterField(
            model_name="platformsettings",
            name="id",
            field=models.UUIDField(
                default=uuid6.uuid7,
                editable=False,
                primary_key=True,
                serialize=False,
            ),
        ),
    ]
