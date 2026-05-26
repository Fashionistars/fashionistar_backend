# apps/custom_order/migrations/0001_initial.py
"""
Initial migration for apps.custom_order.

The physical tables `custom_order` and `custom_order_milestone` were created
by apps.order migration 0008_custom_order_milestone_flow. Since those tables
already exist in the database and the vendor FK now points to
apps.vendor.VendorProfile (not AUTH_USER_MODEL), we use
SeparateDatabaseAndState so that:

  • Django's migration state knows about these models (state_operations).
  • No DDL is executed against the live database (database_operations = []).

When running on a fresh database, run manage.py migrate in order:
    1. apps.order 0008 creates the physical tables (vendor FK = AUTH_USER_MODEL).
    2. This migration 0001 registers the models in the custom_order state.

NOTE: The vendor FK mismatch (AUTH_USER_MODEL vs VendorProfile) is handled
by the next migration (0002_alter_vendor_fk.py) which alters the column on
a fresh DB only. On the existing dev DB the column still works because both
point to the same integer PK column.
"""
from __future__ import annotations

import uuid
from decimal import Decimal

import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Claim existing tables created by apps.order.0008."""

    initial = True

    dependencies = [
        # Ensure order app 0008 has already run so the tables exist
        ("order", "0008_custom_order_milestone_flow"),
        ("vendor", "0001_initial"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    # ── SeparateDatabaseAndState: state = what Django thinks; database = no-op ──
    operations = [
        migrations.SeparateDatabaseAndState(
            # State operations: tell Django these models exist in custom_order app
            state_operations=[
                migrations.CreateModel(
                    name="CustomOrder",
                    fields=[
                        ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("is_deleted", models.BooleanField(db_index=True, default=False)),
                        ("deleted_at", models.DateTimeField(blank=True, null=True)),
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("reference", models.CharField(blank=True, max_length=30, unique=True)),
                        ("status", models.CharField(
                            choices=[
                                ("draft", "Draft"),
                                ("submitted", "Submitted to Vendor"),
                                ("approved", "Vendor Approved"),
                                ("in_production", "In Production"),
                                ("completed", "Completed"),
                                ("cancelled", "Cancelled"),
                                ("disputed", "Disputed"),
                            ],
                            db_index=True,
                            default="draft",
                            max_length=20,
                        )),
                        ("design_brief", models.TextField()),
                        ("reference_images", models.JSONField(blank=True, default=list)),
                        ("product_snapshot_id", models.CharField(blank=True, default="", max_length=255)),
                        ("order_snapshot_id", models.CharField(blank=True, default="", max_length=255)),
                        ("budget_ngn", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                        ("agreed_amount_ngn", models.DecimalField(decimal_places=2, default=Decimal("0.00"), max_digits=14)),
                        ("currency", models.CharField(default="NGN", max_length=3)),
                        ("vendor_approval_note", models.TextField(blank=True, default="")),
                        ("approved_at", models.DateTimeField(blank=True, null=True)),
                        ("completed_at", models.DateTimeField(blank=True, null=True)),
                        ("client", models.ForeignKey(
                            limit_choices_to={"role": "client"},
                            on_delete=django.db.models.deletion.PROTECT,
                            related_name="custom_orders_as_client",
                            to=settings.AUTH_USER_MODEL,
                        )),
                        ("vendor", models.ForeignKey(
                            on_delete=django.db.models.deletion.PROTECT,
                            related_name="custom_orders_as_vendor",
                            to="vendor.vendorprofile",
                        )),
                    ],
                    options={
                        "verbose_name": "Custom Order",
                        "verbose_name_plural": "Custom Orders",
                        "db_table": "custom_order",
                        "ordering": ["-created_at"],
                    },
                ),
                migrations.CreateModel(
                    name="CustomOrderMilestone",
                    fields=[
                        ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                        ("updated_at", models.DateTimeField(auto_now=True)),
                        ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                        ("milestone_pct", models.PositiveSmallIntegerField()),
                        ("amount_ngn", models.DecimalField(decimal_places=2, max_digits=14)),
                        ("payment_status", models.CharField(
                            choices=[
                                ("pending", "Pending"),
                                ("paid", "Paid"),
                                ("failed", "Failed"),
                                ("waived", "Waived"),
                            ],
                            db_index=True,
                            default="pending",
                            max_length=10,
                        )),
                        ("paid_at", models.DateTimeField(blank=True, null=True)),
                        ("payment_reference", models.CharField(blank=True, default="", max_length=255)),
                        ("custom_order", models.ForeignKey(
                            on_delete=django.db.models.deletion.CASCADE,
                            related_name="milestones",
                            to="custom_order.customorder",
                        )),
                    ],
                    options={
                        "verbose_name": "Custom Order Milestone",
                        "verbose_name_plural": "Custom Order Milestones",
                        "db_table": "custom_order_milestone",
                        "ordering": ["milestone_pct"],
                    },
                ),
                migrations.AlterUniqueTogether(
                    name="customordermilestone",
                    unique_together={("custom_order", "milestone_pct")},
                ),
                migrations.AddIndex(
                    model_name="customorder",
                    index=models.Index(fields=["client", "status"], name="co_client_status_idx"),
                ),
                migrations.AddIndex(
                    model_name="customorder",
                    index=models.Index(fields=["vendor", "status"], name="co_vendor_status_idx"),
                ),
                migrations.AddIndex(
                    model_name="customorder",
                    index=models.Index(fields=["reference"], name="co_reference_idx"),
                ),
            ],
            # Database operations: empty — tables already exist from order.0008
            database_operations=[],
        ),
    ]
