# Generated manually for Wave 4 serializer/schema hardening.

import decimal

import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("order", "0004_canonical_order_relationships"),
    ]

    operations = [
        migrations.AlterField(
            model_name="order",
            name="subtotal",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=14,
                validators=[
                    django.core.validators.MinValueValidator(decimal.Decimal("0.00"))
                ],
            ),
        ),
        migrations.AlterField(
            model_name="order",
            name="total_amount",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=14,
                validators=[
                    django.core.validators.MinValueValidator(decimal.Decimal("0.00"))
                ],
            ),
        ),
    ]
