# apps/authentication/migrations/0004_add_client_profile.py
"""
Migration: Add ClientProfile model — 1:1 profile for role='client' users.

Depends on: 0003_add_login_event_user_session
"""
from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion
import django.utils.timezone


class Migration(migrations.Migration):

    dependencies = [
        ("authentication", "0003_add_login_event_user_session"),
    ]

    operations = [
        migrations.CreateModel(
            name="ClientProfile",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created_at",
                    models.DateTimeField(
                        auto_now_add=True,
                        help_text="Timestamp when this record was created.",
                        verbose_name="Created At",
                    ),
                ),
                (
                    "updated_at",
                    models.DateTimeField(
                        auto_now=True,
                        help_text="Timestamp of the last update.",
                        verbose_name="Updated At",
                    ),
                ),
                (
                    "bio",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Short personal bio (max 500 chars).",
                        max_length=500,
                    ),
                ),
                (
                    "default_shipping_address",
                    models.TextField(
                        blank=True,
                        default="",
                        help_text="Default shipping address for checkout.",
                    ),
                ),
                (
                    "state",
                    models.CharField(blank=True, default="", max_length=100),
                ),
                (
                    "country",
                    models.CharField(blank=True, default="Nigeria", max_length=100),
                ),
                (
                    "preferred_size",
                    models.CharField(
                        blank=True,
                        choices=[
                            ("XS", "XS"),
                            ("S", "S"),
                            ("M", "M"),
                            ("L", "L"),
                            ("XL", "XL"),
                            ("XXL", "XXL"),
                            ("XXXL", "XXXL"),
                        ],
                        default="",
                        help_text="Preferred clothing size.",
                        max_length=10,
                    ),
                ),
                (
                    "style_preferences",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text='Style tags: ["casual", "afrocentric", "formal"].',
                    ),
                ),
                (
                    "favourite_colours",
                    models.JSONField(
                        blank=True,
                        default=list,
                        help_text="Favourite colour hex codes or names.",
                    ),
                ),
                (
                    "total_orders",
                    models.PositiveIntegerField(default=0),
                ),
                (
                    "total_spent_ngn",
                    models.DecimalField(decimal_places=2, default=0, max_digits=14),
                ),
                (
                    "is_profile_complete",
                    models.BooleanField(
                        default=False,
                        help_text="True once size, address, and style preferences are filled in.",
                    ),
                ),
                (
                    "user",
                    models.OneToOneField(
                        help_text="The client user this profile belongs to.",
                        limit_choices_to={"role": "client"},
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="client_profile",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name": "Client Profile",
                "verbose_name_plural": "Client Profiles",
                "db_table": "authentication_client_profile",
            },
        ),
        migrations.AddIndex(
            model_name="clientprofile",
            index=models.Index(
                fields=["user"], name="client_profile_user_idx"
            ),
        ),
    ]
