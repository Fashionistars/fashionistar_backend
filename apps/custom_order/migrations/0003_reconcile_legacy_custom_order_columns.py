from django.db import migrations, models


def add_missing_columns(apps, schema_editor):
    CustomOrder = apps.get_model("custom_order", "CustomOrder")
    db_table = CustomOrder._meta.db_table
    
    # Introspect current columns
    with schema_editor.connection.cursor() as cursor:
        columns = [col.name for col in schema_editor.connection.introspection.get_table_description(cursor, db_table)]
    
    # 1. approved_at
    if "approved_at" not in columns:
        field = models.DateTimeField(null=True, blank=True)
        field.set_attributes_from_name("approved_at")
        schema_editor.add_field(CustomOrder, field)
        
    # 2. completed_at
    if "completed_at" not in columns:
        field = models.DateTimeField(null=True, blank=True)
        field.set_attributes_from_name("completed_at")
        schema_editor.add_field(CustomOrder, field)
        
    # 3. currency
    if "currency" not in columns:
        field = models.CharField(max_length=3, default="NGN")
        field.set_attributes_from_name("currency")
        schema_editor.add_field(CustomOrder, field)


class Migration(migrations.Migration):

    dependencies = [
        ("custom_order", "0002_customordermilestone_deleted_at_and_more"),
    ]

    operations = [
        migrations.RunPython(
            code=add_missing_columns,
            reverse_code=migrations.RunPython.noop,
        ),
    ]

