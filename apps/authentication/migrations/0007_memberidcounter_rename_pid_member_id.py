# Generated migration for:
#  1. Create MemberIDCounter table (atomic counter for member_id generation)
#  2. Rename pid → member_id on UnifiedUser
#  3. Alter member_id field (max_length 50→10, db_index=True, editable=False)
#  4. Backfill member_id for any existing users that have NULL

import django.db.models.deletion
from django.db import migrations, models
import django.db.migrations.operations.special


# ──────────────────────────────────────────────
# Backfill RunPython functions
# ──────────────────────────────────────────────

def backfill_member_ids(apps, schema_editor):
    """
    Assign FASTAR-prefixed member IDs to all existing users
    whose member_id is still NULL after the rename migration.

    Counts are updated directly on MemberIDCounter so the live
    counter stays in sync after the backfill completes.
    """
    PREFIX = "FASTAR"
    DIGITS = 4

    UnifiedUser = apps.get_model('authentication', 'UnifiedUser')
    MemberIDCounter = apps.get_model('authentication', 'MemberIDCounter')

    # Get or create the single counter row
    counter_obj, _ = MemberIDCounter.objects.get_or_create(
        id=1, defaults={'counter': 0}
    )
    seq = counter_obj.counter

    users_without_id = (
        UnifiedUser.objects
        .filter(member_id__isnull=True)
        .order_by('date_joined')   # oldest users get lowest numbers
    )

    for user in users_without_id:
        seq += 1
        user.member_id = f"{PREFIX}{seq:0{DIGITS}d}"
        user.save(update_fields=['member_id'])

    # Persist the final counter value
    counter_obj.counter = seq
    counter_obj.save(update_fields=['counter'])


def reverse_backfill_member_ids(apps, schema_editor):
    """
    Undo: set all member_ids back to NULL so the RenameField
    reverse can restore the original pid column.
    """
    UnifiedUser = apps.get_model('authentication', 'UnifiedUser')
    UnifiedUser.objects.update(member_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ('authentication', '0006_alter_unifieduser_first_name_and_more'),
    ]

    operations = [
        # 1. Create the counter table
        migrations.CreateModel(
            name='MemberIDCounter',
            fields=[
                ('id', models.AutoField(
                    auto_created=True,
                    primary_key=True,
                    serialize=False,
                    verbose_name='ID',
                )),
                ('counter', models.PositiveIntegerField(
                    default=0,
                    help_text='Current highest sequence number issued.',
                )),
            ],
            options={
                'verbose_name': 'Member ID Counter',
                'db_table': 'authentication_member_id_counter',
            },
        ),

        # 2. Rename the column: pid → member_id
        migrations.RenameField(
            model_name='unifieduser',
            old_name='pid',
            new_name='member_id',
        ),

        # 3. Alter the field spec (tighten max_length, add db_index)
        migrations.AlterField(
            model_name='unifieduser',
            name='member_id',
            field=models.CharField(
                blank=True,
                db_index=True,
                editable=False,
                help_text=(
                    'Unique human-readable brand ID (e.g. FASTAR0042). '
                    'Auto-generated on user creation. Cannot be changed.'
                ),
                max_length=10,
                null=True,
                unique=True,
            ),
        ),

        # 4. Backfill existing NULL rows
        migrations.RunPython(
            backfill_member_ids,
            reverse_code=reverse_backfill_member_ids,
        ),
    ]
