# apps/common/migrations/0004_add_cloudinary_processed_webhook.py

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('common', '0003_userlifecycle_unique_uuid_and_csv_index_cleanup'),
    ]

    operations = [
        migrations.CreateModel(
            name='CloudinaryProcessedWebhook',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('idempotency_key', models.CharField(db_index=True, help_text='SHA256(public_id + timestamp + asset_type) — prevents duplicates.', max_length=64, unique=True)),
                ('public_id', models.CharField(db_index=True, help_text='Cloudinary public_id (includes folder path).', max_length=500)),
                ('payload_hash', models.CharField(help_text='SHA256 of the original webhook payload — for validation.', max_length=64)),
                ('asset_type', models.CharField(choices=[('image', 'Image'), ('video', 'Video'), ('document', 'Document'), ('unknown', 'Unknown')], db_index=True, help_text='Asset media type (image, video, document).', max_length=30)),
                ('model_target', models.CharField(db_index=True, help_text='Target Django model (avatar, product_image, category_image, etc).', max_length=100)),
                ('model_pk', models.CharField(db_index=True, help_text='PK of the model instance that was updated.', max_length=255)),
                ('secure_url', models.URLField(help_text='Cloudinary secure_url that was saved to the model.', max_length=500)),
                ('success', models.BooleanField(db_index=True, default=True, help_text='Whether webhook processing succeeded.')),
                ('error_message', models.TextField(blank=True, help_text='Error message if processing failed.', null=True)),
                ('processing_time_ms', models.FloatField(default=0.0, help_text='How long webhook processing took (milliseconds).')),
                ('processed_at', models.DateTimeField(auto_now_add=True, db_index=True, help_text='When the webhook was received and processed.')),
                ('created_at', models.DateTimeField(auto_now_add=True, help_text='When this audit record was created.')),
                ('updated_at', models.DateTimeField(auto_now=True, help_text='When this record was last updated (should rarely happen).')),
            ],
            options={
                'verbose_name': 'Cloudinary Processed Webhook',
                'verbose_name_plural': 'Cloudinary Processed Webhooks',
                'db_table': 'cloudinary_processed_webhooks',
                'ordering': ['-processed_at'],
                'permissions': [('view_webhook', 'Can view processed webhooks')],
            },
        ),
        migrations.AddIndex(
            model_name='cloudinaryprocessedwebhook',
            index=models.Index(fields=['public_id'], name='cloudinary_p_public_d73d8c_idx'),
        ),
        migrations.AddIndex(
            model_name='cloudinaryprocessedwebhook',
            index=models.Index(fields=['model_target', 'model_pk'], name='cloudinary_p_model_t_e1a2f3_idx'),
        ),
        migrations.AddIndex(
            model_name='cloudinaryprocessedwebhook',
            index=models.Index(fields=['asset_type'], name='cloudinary_p_asset_t_b4c5d6_idx'),
        ),
        migrations.AddIndex(
            model_name='cloudinaryprocessedwebhook',
            index=models.Index(fields=['processed_at'], name='cloudinary_p_proceed_a7b8c9_idx'),
        ),
        migrations.AddIndex(
            model_name='cloudinaryprocessedwebhook',
            index=models.Index(fields=['-processed_at'], name='cloudinary_p_proceed_d1e2f3_idx'),
        ),
        migrations.AddIndex(
            model_name='cloudinaryprocessedwebhook',
            index=models.Index(fields=['success', 'processed_at'], name='cloudinary_p_success_g4h5i6_idx'),
        ),
    ]
