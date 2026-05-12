from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("order", "0003_canonical_cart_order_item_snapshots"),
        ("product", "0003_phase1_enterprise_expansion"),
        ("vendor", "0002_fix_cartitem_related_name_to_items"),
    ]

    operations = [
        migrations.RenameField(
            model_name="order",
            old_name="courier",
            new_name="delivery_courier",
        ),
        migrations.AddField(
            model_name="order",
            name="customization_notes",
            field=models.TextField(
                blank=True,
                help_text="Any special notes from the customer about the custom order.",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="is_custom_order",
            field=models.BooleanField(
                default=False,
                help_text="True if this is a fully custom-made item (not pre-made).",
            ),
        ),
        migrations.AddField(
            model_name="order",
            name="measurement_data",
            field=models.JSONField(
                blank=True,
                default=dict,
                help_text="Snapshot of customer measurements (height, weight, bust, etc.)",
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="delivery_courier",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="delivery_courier_orders",
                to="product.deliverycourier",
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="user",
            field=models.ForeignKey(
                blank=True,
                help_text="SET_NULL: order history preserved for financial audit after user deletion.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="user_orders",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="vendor",
            field=models.ForeignKey(
                blank=True,
                help_text="SET_NULL: order history preserved after vendor departure.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="vendor_orders",
                to="vendor.vendorprofile",
            ),
        ),
        migrations.AlterField(
            model_name="orderidempotencyrecord",
            name="order",
            field=models.OneToOneField(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="order_idempotency_record",
                to="order.order",
            ),
        ),
        migrations.AlterField(
            model_name="orderstatushistory",
            name="actor",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="order_status_history_actor",
                to=settings.AUTH_USER_MODEL,
            ),
        ),
        migrations.AlterField(
            model_name="orderstatushistory",
            name="order",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                related_name="order_status_history",
                to="order.order",
            ),
        ),
        migrations.DeleteModel(name="OrderItem"),
    ]
