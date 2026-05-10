# Generated (patched) — 2026-05-05
#
# The Collection model was renamed to Collections in code.
# The underlying DB table was already renamed to `catalog_collections`
# in migration 0002.  This migration records the model rename as a
# state-only operation so Django's migration framework is kept in sync
# without touching the database.

from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('catalog', '0002_alter_collection_table'),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # No database changes needed — table already exists as catalog_collections.
            database_operations=[],
            state_operations=[
                migrations.RenameModel(
                    old_name='Collection',
                    new_name='Collections',
                ),
            ],
        ),
    ]
