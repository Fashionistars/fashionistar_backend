# Generated by Django 4.2.7 on 2024-07-19 00:11

from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
    ]

    operations = [
        migrations.CreateModel(
            name='CancelledOrder',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.CharField(max_length=100)),
                ('refunded', models.BooleanField(default=False)),
            ],
            options={
                'verbose_name_plural': 'Cancelled Orders',
            },
        ),
        migrations.CreateModel(
            name='Notification',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('notification_type', models.CharField(choices=[('new_order', 'New Order'), ('new_offer', 'New Offer'), ('new_bidding', 'New Bidding'), ('item_arrived', 'Item Arrived'), ('item_shipped', 'Item Shipped'), ('item_delivered', 'Item Delivered'), ('tracking_id_added', 'Tracking ID Added'), ('tracking_id_changed', 'Tracking ID Changed'), ('offer_rejected', 'Offer Rejected'), ('offer_accepted', 'Offer Accepted'), ('update_offer', 'Update Offer'), ('update_bid', 'Update Bid'), ('order_cancelled', 'Order Cancelled'), ('order_cancel_request', 'Order Cancel Request'), ('new_review', 'New Review'), ('noti_new_faq', 'New Product Question'), ('bidding_won', 'Bidding Won'), ('product_published', 'Product Published'), ('product_rejected', 'Product Rejected'), ('product_disabled', 'Product Disabled')], max_length=50)),
                ('seen', models.BooleanField(default=False)),
                ('date', models.DateTimeField(auto_now_add=True)),
            ],
            options={
                'verbose_name_plural': 'Notifications',
            },
        ),
    ]