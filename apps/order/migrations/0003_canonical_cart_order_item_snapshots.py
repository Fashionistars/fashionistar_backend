from decimal import Decimal

import cloudinary.models
import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("order", "0002_add_cart_order_item"),
        ("vendor", "0002_fix_cartitem_related_name_to_items"),
    ]

    operations = [
        migrations.RenameField(
            model_name="cartorderitem",
            old_name="sku_snapshot",
            new_name="product_sku_snapshot",
        ),
        migrations.RenameField(
            model_name="cartorderitem",
            old_name="title_snapshot",
            new_name="product_title_snapshot",
        ),
        migrations.RenameField(
            model_name="cartorderitem",
            old_name="variant_snapshot",
            new_name="variant_description_snapshot",
        ),
        migrations.RenameField(
            model_name="cartorderitem",
            old_name="cover_image_url",
            new_name="cover_image_snapshot",
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="customization_notes",
            field=models.TextField(
                blank=True,
                help_text="Any special notes from the customer about the custom order.",
            ),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="is_custom_order",
            field=models.BooleanField(
                default=False,
                help_text="True if this is a fully custom-made item (not pre-made).",
            ),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="measurement_data",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Snapshot of customer measurements (height, weight, bust, etc.)",
            ),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="variant_images_snapshot",
            field=cloudinary.models.CloudinaryField(
                blank=True,
                help_text="Cloudinary URL of product variant images at order time.",
                max_length=255,
                verbose_name="variant_images_snapshot",
            ),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                help_text="SET_NULL: snapshot preserved if vendor is deleted.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cart_order_vendor_snapshots",
                to="vendor.vendorprofile",
            ),
        ),
        migrations.AddField(
            model_name="cartorderitem",
            name="vendor_name_snapshot",
            field=models.CharField(
                blank=True,
                help_text="Vendor name at time of order.",
                max_length=200,
            ),
        ),
        migrations.AlterField(
            model_name="cartorderitem",
            name="cover_image_snapshot",
            field=cloudinary.models.CloudinaryField(
                blank=True,
                help_text="Cloudinary URL of product cover image at order time.",
                max_length=255,
                verbose_name="cover_image_snapshot",
            ),
        ),
        migrations.AlterField(
            model_name="cartorderitem",
            name="product",
            field=models.ForeignKey(
                blank=True,
                help_text="SET_NULL: snapshot preserved if product is deleted.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cart_order_product_snapshots",
                to="product.product",
            ),
        ),
        migrations.AlterField(
            model_name="cartorderitem",
            name="variant",
            field=models.ForeignKey(
                blank=True,
                help_text="SET_NULL: snapshot preserved if variant is deleted.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="cart_order_variant_snapshots",
                to="product.productvariant",
            ),
        ),
        migrations.AlterField(
            model_name="cartorderitem",
            name="commission_amount",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                help_text="commission_rate / 100 × line_total, frozen at placement.",
                max_digits=12,
            ),
        ),
        migrations.AlterField(
            model_name="cartorderitem",
            name="line_total",
            field=models.DecimalField(
                decimal_places=2,
                help_text="unit_price × quantity, frozen at placement.",
                max_digits=14,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
    ]
