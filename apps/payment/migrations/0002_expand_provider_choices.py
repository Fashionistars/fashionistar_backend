# Generated manually for Wave 4 provider-boundary normalization.

from django.db import migrations, models


PROVIDER_CHOICES = [
    ("paystack", "Paystack"),
    ("flutterwave", "flutterwave"),
    ("stripe", "stripe"),
    ("paypal", "paypal"),
    ("cash", "cash"),
    ("bank_transfer", "bank_transfer"),
    ("ussd", "ussd"),
    ("qr", "qr"),
    ("wallet", "wallet"),
    ("card", "card"),
    ("gift_card", "gift_card"),
    ("bank_deposit", "bank_deposit"),
    ("voucher", "voucher"),
    ("app", "app"),
    ("cod", "cod"),
    ("others", "others"),
    ("olive_pay", "olive_pay"),
]


class Migration(migrations.Migration):

    dependencies = [
        ("payment", "0001_initial"),
    ]

    operations = [
        migrations.AlterField(
            model_name="paymentintent",
            name="provider",
            field=models.CharField(
                choices=PROVIDER_CHOICES,
                db_index=True,
                default="paystack",
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name="paymentprovider",
            name="code",
            field=models.CharField(
                choices=PROVIDER_CHOICES,
                max_length=40,
                unique=True,
            ),
        ),
        migrations.AlterField(
            model_name="paymentproviderlog",
            name="provider",
            field=models.CharField(
                choices=PROVIDER_CHOICES,
                db_index=True,
                max_length=40,
            ),
        ),
        migrations.AlterField(
            model_name="paymentwebhookevent",
            name="provider",
            field=models.CharField(
                choices=PROVIDER_CHOICES,
                db_index=True,
                max_length=40,
            ),
        ),
    ]
