from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("product", "0005_fix_cartitem_related_name_to_items"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="product",
            name="idx_product_category",
        ),
    ]
