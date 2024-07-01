# Generated by Django 4.2.7 on 2024-07-01 15:16

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        ('vendor', '0001_initial'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('store', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(choices=[('new_order', 'New Order'), ('new_offer', 'New Offer'), ('new_bidding', 'New Bidding'), ('item_arrived', 'Item Arrived'), ('item_shipped', 'Item Shipped'), ('item_delivered', 'Item Delivered'), ('tracking_id_added', 'Tracking ID Added'), ('tracking_id_changed', 'Tracking ID Changed'), ('offer_rejected', 'Offer Rejected'), ('offer_accepted', 'Offer Accepted'), ('update_offer', 'Update Offer'), ('update_bid', 'Update Bid'), ('order_cancelled', 'Order Cancelled'), ('order_cancel_request', 'Order Cancel Request'), ('new_review', 'New Review'), ('noti_new_faq', 'New Product Question'), ('bidding_won', 'Bidding Won'), ('product_published', 'Product Published'), ('product_rejected', 'Product Rejected'), ('product_disabled', 'Product Disabled')], max_length=50)),
                ('seen', models.BooleanField(default=False)),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('order', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='store.cartorder')),
                ('order_item', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='store.cartorderitem')),
                ('user', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to=settings.AUTH_USER_MODEL)),
                ('vendor', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, to='vendor.vendor')),
            ],
            options={
                'verbose_name_plural': 'Notifications',
            },
        ),
        migrations.CreateModel(
            name='CancelledOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.CharField(max_length=100)),
                ('refunded', models.BooleanField(default=False)),
                ('orderitem', models.ForeignKey(null=True, on_delete=django.db.models.deletion.SET_NULL, to='store.cartorderitem')),
                ('user', models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Cancelled Orders',
            },
        ),
    ]
