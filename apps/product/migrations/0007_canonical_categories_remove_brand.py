from django.db import migrations, models


def copy_legacy_category_fks(apps, schema_editor):
    """Copy legacy single category FKs into the canonical M2M through tables."""
    Product = apps.get_model("product", "Product")
    db_alias = schema_editor.connection.alias

    category_through = Product.categories.through
    sub_category_through = Product.sub_categories.through

    category_rows = []
    sub_category_rows = []
    for product in Product.objects.using(db_alias).only(
        "id", "category_id", "sub_category_id"
    ).iterator():
        if product.category_id:
            category_rows.append(
                category_through(product_id=product.pk, category_id=product.category_id)
            )
        if product.sub_category_id:
            sub_category_rows.append(
                sub_category_through(
                    product_id=product.pk,
                    category_id=product.sub_category_id,
                )
            )

    category_through.objects.using(db_alias).bulk_create(
        category_rows,
        ignore_conflicts=True,
        batch_size=1000,
    )
    sub_category_through.objects.using(db_alias).bulk_create(
        sub_category_rows,
        ignore_conflicts=True,
        batch_size=1000,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("catalog", "0003_fix_cartitem_related_name_to_items"),
        ("product", "0006_remove_product_m2m_category_index"),
    ]

    operations = [
        migrations.AddField(
            model_name="product",
            name="categories",
            field=models.ManyToManyField(
                help_text=(
                    "Canonical product categories. Service layer enforces "
                    "1-5 selections."
                ),
                related_name="category_products",
                to="catalog.category",
            ),
        ),
        migrations.AddField(
            model_name="product",
            name="sub_categories",
            field=models.ManyToManyField(
                blank=True,
                help_text=(
                    "Optional deeper taxonomy facets. Kept separate from "
                    "required categories."
                ),
                related_name="sub_category_products",
                to="catalog.category",
            ),
        ),
        migrations.RunPython(copy_legacy_category_fks, migrations.RunPython.noop),
        migrations.RemoveField(
            model_name="product",
            name="category",
        ),
        migrations.RemoveField(
            model_name="product",
            name="sub_category",
        ),
        migrations.RemoveField(
            model_name="product",
            name="brand",
        ),
    ]
