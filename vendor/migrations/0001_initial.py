# Generated by Django 4.2.7 on 2024-04-25 02:21

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import shortuuid.django_fields
import userauths.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='Vendor',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('image', models.ImageField(blank=True, default='shop-image.jpg', upload_to=userauths.models.user_directory_path)),
                ('name', models.CharField(blank=True, help_text='Shop Name', max_length=100, null=True)),
                ('email', models.EmailField(blank=True, help_text='Shop Email', max_length=100, null=True)),
                ('description', models.TextField(blank=True, null=True)),
                ('mobile', models.CharField(blank=True, max_length=150, null=True)),
                ('verified', models.BooleanField(default=False)),
                ('active', models.BooleanField(default=True)),
                ('vid', shortuuid.django_fields.ShortUUIDField(alphabet='abcdefghijklmnopqrstuvxyz', length=10, max_length=20, prefix='', unique=True)),
                ('date', models.DateTimeField(auto_now_add=True)),
                ('slug', models.SlugField(blank=True, null=True)),
                ('user', models.OneToOneField(null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='vendor', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'verbose_name_plural': 'Vendors',
            },
        ),
    ]
