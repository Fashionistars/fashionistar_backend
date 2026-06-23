from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('order', '0014_cartorderitem_active_discountcode_active_and_more'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
            DROP TABLE IF EXISTS cart_cartactivitylog CASCADE;
            DROP TABLE IF EXISTS cart_cartitem CASCADE;
            DROP TABLE IF EXISTS cart_cart CASCADE;
            """,
            reverse_sql=""
        )
    ]
