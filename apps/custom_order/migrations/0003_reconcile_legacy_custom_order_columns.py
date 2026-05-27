from django.db import migrations


ADD_MISSING_COLUMNS_SQL = """
ALTER TABLE custom_order
    ADD COLUMN IF NOT EXISTS approved_at timestamptz NULL,
    ADD COLUMN IF NOT EXISTS completed_at timestamptz NULL,
    ADD COLUMN IF NOT EXISTS currency varchar(3);

UPDATE custom_order
SET currency = 'NGN'
WHERE currency IS NULL;

ALTER TABLE custom_order
    ALTER COLUMN currency SET DEFAULT 'NGN',
    ALTER COLUMN currency SET NOT NULL;
"""


class Migration(migrations.Migration):

    dependencies = [
        ("custom_order", "0002_customordermilestone_deleted_at_and_more"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunSQL(
                    sql=ADD_MISSING_COLUMNS_SQL,
                    reverse_sql=migrations.RunSQL.noop,
                ),
            ],
            state_operations=[],
        ),
    ]
